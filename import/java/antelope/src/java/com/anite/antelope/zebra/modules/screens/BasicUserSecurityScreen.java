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

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.modules.screens.TemplateScreen;
import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AntelopeConstants;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Base Screen for all workflow screens This will check workflow security, call
 * down to child with modified doBuildTemplate with workflow information and
 * populate
 * 
 * @author Ben.Gidley
 */
public abstract class BasicUserSecurityScreen extends VelocityScreen {

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
	protected abstract void doBuildUserAuthorisedTemplate(RunData runData, Context context,
			 FormTool tool) throws Exception;

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
	protected final boolean isAuthorized( Context context)
			throws ComponentException, NestableException, UnknownEntityException {

	
	

		UserManager manager = AvalonServiceHelper.instance().getSecurityService().getUserManager();
		DynamicAccessControlList acl = (DynamicAccessControlList) manager.getACL(UserLocator
				.getLoggedInUser());

	

	return acl.hasPermission(AntelopeConstants.PERMISSION_SYSTEM_ACCESS);
		
	
	}

	/**
	 * @param pipelineData
	 * @param context
	 */
	public void redirectToTaskList(RunData data, Context context) {

		// redirect to task list
		TemplateScreen.setTemplate(data, ZebraHelper.getInstance().getTaskListScreenName());
		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		form.reinitialiseForScreenEndpoint();
	}

	/**
	 * This has a lot of commented out code as I wrote the code to use the
	 * Pipeline data version of doBuildTemplate but then found a bug in the base
	 * classes
	 * 
	 * @see org.apache.turbine.modules.screens.VelocityScreen#doBuildTemplate(org.apache.turbine.util.RunData,
	 *      org.apache.velocity.context.Context)
	 */
	protected void doBuildTemplate(RunData data, Context context) throws Exception {

		// RunData data = this.getRunData(pipelineData);

		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		
		if (isAuthorized(context)){
			doBuildUserAuthorisedTemplate(data,context,form);
		} else {
			redirectToTaskList(data, context);
		}
	}
	
	/**
	 * Trys to restore a taskinstace property set from the process property set if
	 * one has been persisted for this task definition
	 * @param taskInstance
	 */
	private void tryToloadTaskInstancePropertySet(AntelopeTaskInstance taskInstance){
	    String key = taskInstance.getTaskDefinition().getId().toString();
	    if (taskInstance.getProcessPropertySet().containsKey(key)){
	        AntelopePropertySetEntry entry = (AntelopePropertySetEntry) taskInstance.getProcessPropertySet().get(key);	        
	        Map restoredProperties = (Map) entry.getObject();
	        taskInstance.getProcessPropertySet().remove(key);
	        taskInstance.getPropertySet().clear();
	        
	        for (Iterator iter = restoredProperties.keySet().iterator(); iter.hasNext();) {                
	            // These line are because we are trying to make sure hibernate assigns a new ID
	            String restoredKey = (String) iter.next();
	            AntelopePropertySetEntry restoredEntry = (AntelopePropertySetEntry) restoredProperties.get(restoredKey);
	            AntelopePropertySetEntry clonedEntry = new AntelopePropertySetEntry();
	            clonedEntry.setValue(restoredEntry.getValue());
	            clonedEntry.setObject(restoredEntry.getObject());
                taskInstance.getPropertySet().put(restoredKey, clonedEntry);
            }
	    }
	}
}