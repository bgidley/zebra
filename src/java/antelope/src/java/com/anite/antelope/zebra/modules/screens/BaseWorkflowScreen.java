/*
 * Copyright 2004 Anite - Central Government Division
 *    http://www.anite.com/publicsector
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.anite.antelope.zebra.modules.screens;

import java.util.Iterator;
import java.util.Map;

import net.sf.hibernate.HibernateException;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.modules.ScreenLoader;
import org.apache.turbine.modules.screens.TemplateScreen;
import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceException;
import com.anite.penguin.modules.tools.FormTool;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * Base Screen for all workflow screens This will check workflow security, call
 * down to child with modified doBuildTemplate with workflow information and
 * populate
 * 
 * @author Ben.Gidley
 */
public abstract class BaseWorkflowScreen extends VelocityScreen {

    private static Log log = LogFactory.getLog(BaseWorkflowScreen.class);

    /**
     * Prepare the form TODO revise this for pipeline data once things have
     * settled down
     * 
     * @param runData
     * @param context
     * @param taskInstance
     * @throws Exception
     */
    protected abstract void doBuildTemplate(RunData runData, Context context,
            AntelopeTaskInstance taskInstance, FormTool form) throws Exception;

    /**
     * Called if the child throws something Can be overidden to provide a
     * friendly error page This default just throws it upwards
     * 
     * @param e
     */
    protected void handleException(Exception e) throws Exception {

        throw (e);
    }

    /**
     * If present load paused form data from TaskInstance As an optimisation if
     * the context contains KEEP_FORM value then the previous action has
     * indicated we do not need to do this.
     * 
     * @param taskInstance
     * @param form
     */
    private FormTool loadPausedFormData(AntelopeTaskInstance taskInstance,
            FormTool form, Context context) {

        if (taskInstance.getPropertySet().containsKey(
                AntelopeTaskInstance.PAUSED_FORM_DETAILS)) {
            form = setFormTool(
                    (FormTool) ((AntelopePropertySetEntry) taskInstance
                            .getPropertySet().get(
                                    AntelopeTaskInstance.PAUSED_FORM_DETAILS))
                            .getObject(), context);
        }

        return form;
    }

    /**
     * @param taskInstance
     * @param context
     * @return
     */
    public FormTool setFormTool(FormTool form, Context context) {

        context.put(FormTool.DEFAULT_TOOL_NAME, form);
        return form;
    }

    /**
     * Check if use can see this workflow screen
     * 
     * @return @throws
     *         ComponentException
     * @throws NestableException
     * @throws UnknownEntityException
     */
    protected final boolean isAuthorized(AntelopeTaskInstance taskInstance,
            Context context) throws ComponentException, NestableException,
            UnknownEntityException {

        //Do workflow security checks
        Iterator taskPermissions = taskInstance.getPermissions().iterator();

        UserManager manager = AvalonServiceHelper.instance()
                .getSecurityService().getUserManager();
        DynamicAccessControlList acl = (DynamicAccessControlList) manager
                .getACL(UserLocator.getLoggedInUser());

        boolean permitted = false;
        while (taskPermissions.hasNext()) {
            if (acl.hasPermission((Permission) taskPermissions.next())) {
                permitted = true;
                break;
            }
        }

        if (permitted) {
            //	Next Check Ownership
            if (taskInstance.getTaskOwner() == null) {
                taskInstance.setTaskOwner(UserLocator.getLoggedInUser());

                ITransaction t = ZebraHelper.getInstance().getStateFactory()
                        .beginTransaction();
                ZebraHelper.getInstance().getStateFactory().saveObject(
                        taskInstance);
                t.commit();

            } else {
                if (taskInstance.getTaskOwner() != UserLocator
                        .getLoggedInUser()) {
                    return false;
                }
            }
        }
        return permitted;
    }

    /**
     * @param pipelineData
     * @param context
     * @throws Exception
     */
    public void redirectToTaskList(RunData data, Context context)
            throws Exception {

        // redirect to task list
        TemplateScreen.setTemplate(data, ZebraHelper.getInstance()
                .getTaskListScreenName());

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        form.reinitialiseForScreenEndpoint();
        ScreenLoader.getInstance().exec(data,
                ZebraHelper.getInstance().getTaskListScreen());
    }

    /**
     * This has a lot of commented out code as I wrote the code to use the
     * Pipeline data version of doBuildTemplate but then found a bug in the base
     * classes
     * 
     * @see org.apache.turbine.modules.screens.VelocityScreen#doBuildTemplate(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context)
     */
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {

        // RunData data = this.getRunData(pipelineData);

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        ZebraSessionData sessionData = (ZebraSessionData) data.getSession()
                .getAttribute(ZebraSessionData.SESSION_KEY);

        if (sessionData == null) {
            // I think this will only happen if someone bookmarks the middle of
            // a flow
            // Which they shouldn't be doing (also the filters should have
            // stopped
            // them getting this far).
            log
                    .info("Someone has tried to run a workflow screen without a session:"
                            + data.getScreenTemplate());
            redirectToTaskList(data, context);
            return;
        }

        AntelopeTaskInstance taskInstance = sessionData.getTaskInstance();

        if (isAuthorized(taskInstance, context)) {
            if (log.isDebugEnabled()) {
                log.debug(form);
                log.debug(sessionData);
            }

            tryToloadTaskInstancePropertySet(taskInstance);
            form = loadPausedFormData(taskInstance, form, context);

            try {
                doBuildTemplate(data, context, sessionData.getTaskInstance(),
                        form);
            } catch (Exception e) {
                log.error(null, e);
                handleException(e);
            }
        } else {
            redirectToTaskList(data, context);
        }
    }

    /**
     * Trys to restore a taskinstace property set from the process property set
     * if one has been persisted for this task definition
     * 
     * @param taskInstance
     * @throws HibernateException
     * @throws PersistenceException
     */
    private void tryToloadTaskInstancePropertySet(
            AntelopeTaskInstance taskInstance) throws PersistenceException,
            HibernateException {
        String key = taskInstance.getTaskDefinition().getId().toString();
        if (taskInstance.getProcessPropertySet().containsKey(key)) {
            AntelopePropertySetEntry entry = (AntelopePropertySetEntry) taskInstance
                    .getProcessPropertySet().get(key);
            Map restoredProperties = (Map) entry.getObject();
            taskInstance.getProcessPropertySet().remove(key);
            taskInstance.getPropertySet().clear();

            for (Iterator iter = restoredProperties.keySet().iterator(); iter
                    .hasNext();) {
                // These line are because we are trying to make sure hibernate
                // assigns a new ID
                String restoredKey = (String) iter.next();
                AntelopePropertySetEntry restoredEntry = (AntelopePropertySetEntry) restoredProperties
                        .get(restoredKey);
                AntelopePropertySetEntry clonedEntry = new AntelopePropertySetEntry();
                clonedEntry.setValue(restoredEntry.getValue());
                clonedEntry.setObject(restoredEntry.getObject());
                taskInstance.getPropertySet().put(restoredKey, clonedEntry);
            }

            doRestore(taskInstance);
        }
    }

    /**
     * Override me to reset stuff when restoring after visitng another screen.
     *  
     */
    public void doRestore(AntelopeTaskInstance taskInstance)
            throws PersistenceException, HibernateException {
        // noop
    }
}