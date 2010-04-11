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

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.modules.actions.VelocityAction;
import org.apache.turbine.modules.screens.TemplateScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AntelopeConstants;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Base Screen for all workflow screens This will check workflow security, call
 * down to child with modified doBuildTemplate with workflow information and
 * populate
 * 
 * @author Ben.Gidley
 */
public abstract class BasicUserSecurityAction extends VelocityAction {

	private static Log log = LogFactory.getLog(BaseWorkflowAction.class);

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


	/* (non-Javadoc)
	 * @see org.apache.turbine.modules.actions.VelocityAction#doPerform(org.apache.turbine.util.RunData, org.apache.velocity.context.Context)
	 */
	public void doPerform(RunData data, Context context) throws Exception {
		

		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		
		if (isAuthorized(context)){
			doBuildUserAuthorisedTemplate(data,context,form);
		} else {
			redirectToTaskList(data, context);
		}
	
	}
}