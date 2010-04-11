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

package com.anite.antelope.zebra.modules.actions;

import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import net.sf.hibernate.HibernateException;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceException;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Ben.Gidley
 */
public abstract class BaseWorkflowAction extends AbstractWorkflowRunTaskAction {

    public static final String PAUSE_NAME = "pause";

    public static final String CANCEL_NAME = "cancel";

    public static final String DONE_NAME = "done";

    public static final String HOME_NAME = "home";

    private static Log log = LogFactory.getLog(BaseWorkflowAction.class); //$SUP-HIA$

    public final void doPerform(RunData data, Context context) throws Exception {
        ZebraSessionData sessionData = (ZebraSessionData) data.getSession()
                .getAttribute(ZebraSessionData.SESSION_KEY);

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        AntelopeTaskInstance taskInstance = sessionData.getTaskInstance();
        AntelopeProcessInstance processInstance = (AntelopeProcessInstance) taskInstance
                .getProcessInstance();

        // Which button was pressed
        if (!(((Field) form.getFields().get(PAUSE_NAME)).getValue().equals(""))) {
            pauseForm(form, taskInstance, processInstance);
            goToTaskList(data, form);
            return;
        } else if (!(((Field) form.getFields().get(CANCEL_NAME)).getValue()
                .equals(""))) {
            // Cancel Pressed
            doCancel(taskInstance, processInstance, form);
            goToTaskList(data, form);
            return;
        } else if (!(((Field) form.getFields().get(HOME_NAME)).getValue()
                .equals(""))) {
            // Home pressed so go to task list and let child decide what to do
            if (doHome(taskInstance, form)) {
                saveTask(taskInstance);
                transistion(taskInstance);
            }
            goToTaskList(data, form);
            return;
        } else {
            

            if (enforceValidation()) {
                if (!form.isAllValid()) {
                    savePauseInformation(taskInstance, form);
                    this.setTemplate(data,
                            ((AntelopeTaskDefinition) taskInstance
                                    .getTaskDefinition()).getScreenName());
                    return;
                }
            }

            boolean transition = false;
            try {
                transition = doPerform(data, context, taskInstance,
                        processInstance, form);

                saveTask(taskInstance);
            } catch (Exception e) {
                savePauseInformation(taskInstance, form);
                log.error("Child Action Exception", e);
                handleException(e);
                return;
            }

            if (transition) {
                transistion(taskInstance);
                determineNextScreen(data, form, processInstance, context);
            } else {                
                this.setTemplate(data, ((AntelopeTaskDefinition) taskInstance
                        .getTaskDefinition()).getScreenName());
                savePauseInformation(taskInstance, form);
            }
        }
    }

    /**
     * @param taskInstance
     * @param processInstance
     * @throws StateFailureException
     * @throws ComponentException
     */
    private void saveTask(AntelopeTaskInstance taskInstance)
            throws StateFailureException, ComponentException {
        //Save the task Instance
        ITransaction t = ZebraHelper.getInstance().getStateFactory()
                .beginTransaction();
        ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance);
        ZebraHelper.getInstance().getStateFactory().saveObject(
                taskInstance.getAntelopeProcessInstance());
        t.commit();
    }

    /**
     * @param taskInstance
     * @throws TransitionException
     * @throws ComponentException
     */
    private void transistion(AntelopeTaskInstance taskInstance)
            throws TransitionException, ComponentException {
        // Set task properties
        taskInstance.setActualCompletionDate(new Date(System
                .currentTimeMillis()));
        taskInstance.setDecisionMadeBy(UserLocator.getLoggedInUser());
        taskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);

        //Task is ready to move on
        ZebraHelper.getInstance().getEngine().transitionTask(taskInstance);
    }

    /**
     * Do the work for pausing a form (but don't redirect)
     * 
     * @param form
     * @param taskInstance
     * @param processInstance
     * @throws StateFailureException
     * @throws ComponentException
     */
    private void pauseForm(FormTool form, AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance)
            throws StateFailureException, ComponentException {
        doPause(taskInstance, processInstance, form);
        // Pause Pressed
        savePauseInformation(taskInstance, form);
    }

    /**
     * @param data
     */
    private void goToTaskList(RunData data, FormTool form) {
        // Go to task list
        setTemplate(data, ZebraHelper.getInstance().getTaskListScreenName());
        form.reinitialiseForScreenEndpoint();
    }

    /**
     * Child classes implement this to validate and provide business logic. The
     * system will advance if the state on the task is set to
     * ITaskInstance.STATE_READY
     * 
     * @param runData
     * @param context
     * @param taskInstance
     * @param tool
     * @return True if we should transition
     * @throws Exception
     */
    protected abstract boolean doPerform(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception;

    /**
     * Called before pause information has been saved and before redirecting to
     * task list.
     * 
     * By default does nothing.
     * 
     * Can be used to change/modify information about to be paused. Don't try
     * and transition/kill workflows here - it will be messy. Use do Cancel for
     * that.
     * 
     * You are not given Turbine stuff here to play with - because it will be a
     * bad idea. So don't store them as class variables and play with things
     * 
     * @param taskInstance
     * @param processInstance
     * @param tool
     */
    protected void doPause(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool from) {
        // Noop
    }

    /**
     * Called immediately prior to redirect to task list Default do nothing
     * Overide if you want to do some work e.g. killing the task You are not
     * given Turbine stuff here to play with - because it will be a bad idea. So
     * don't store them as class variables and play with things
     *  
     */
    protected void doCancel(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form) {
        //Noop
    }

    /**
     * Called immediately prior to redirect to task list Default do pause
     * Overide if you want to do some work e.g. killing the task You are not
     * given Turbine stuff here to play with - because it will be a bad idea. So
     * don't store them as class variables and play with things
     * 
     * @throws ComponentException
     * @throws StateFailureException
     * @return true if the task should transition
     */
    protected boolean doHome(AntelopeTaskInstance taskInstance, FormTool form)
            throws StateFailureException, ComponentException {
        pauseForm(form, taskInstance, taskInstance.getAntelopeProcessInstance());
        return false;
    }

    /**
     * If the child action wishes the parent to not call it if the form it not
     * valid return true here.
     * 
     * @return
     */
    protected abstract boolean enforceValidation();

    /**
     * Check workflow security
     */
    protected boolean isAuthorized(RunData data) throws Exception {
        // TODO implement workflow security
        return true;
    }

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
     * Saves the form information into the taskInstance property set
     * 
     * @param form
     * @param taskInstance
     * @throws ComponentException
     * @throws StateFailureException
     */
    private void savePauseInformation(AntelopeTaskInstance taskInstance,
            FormTool form) throws StateFailureException, ComponentException {
        taskInstance.getPropertySet().put(
                AntelopeTaskInstance.PAUSED_FORM_DETAILS,
                new AntelopePropertySetEntry(form));
        ITransaction transaction = ZebraHelper.getInstance().getStateFactory()
                .beginTransaction();
        ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance);
        transaction.commit();
    }

    /**
     * If you are going off to a subflow and want to come back to this screen
     * with the task instance properties intact call this function before going
     * off. This will store the taskInstance in the property set. This will also
     * savePauseInformation. So make sure you have done everything you want to
     * do to the formTool before called this.
     * 
     * @param taskInstance
     * @throws ComponentException
     * @throws StateFailureException
     * @throws PersistenceException
     * @throws HibernateException
     */
    public void saveTaskInstancePropertySet(AntelopeTaskInstance taskInstance,
            FormTool form) throws StateFailureException, ComponentException,
            PersistenceException, HibernateException {
        
        form.setReinitialise(false);
        savePauseInformation(taskInstance, form);

        
        
        ITransaction tx = ZebraHelper.getInstance().getStateFactory()
                .beginTransaction();
        AntelopePropertySetEntry entry = new AntelopePropertySetEntry();
        // Take a COPY of the map (otherwise hibernate will complain)		
        Map map = new HashMap(taskInstance.getPropertySet());
        entry.setObject(map);
        String key = taskInstance.getTaskDefinition().getId().toString();
        taskInstance.getProcessPropertySet().put(key, entry);
        ZebraHelper.getInstance().getStateFactory().saveObject(
                taskInstance.getAntelopeProcessInstance());
        tx.commit();
    }
}