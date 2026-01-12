/*
 * Copyright 2004 Anite - Central Government Division
 * http://www.anite.com/publicsector
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 * 
 * http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */
package com.anite.antelope.modules.screens.security;

import org.apache.commons.lang.StringUtils;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.SecureScreen;
import com.anite.antelope.modules.tools.SecurityTool;
import com.anite.antelope.utils.PermissionHelper;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class Groups extends SecureScreen {

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.modules.screens.VelocitySecureScreen#doBuildTemplate(org.apache.turbine.util.RunData,
	 *      org.apache.velocity.context.Context)
	 */
	protected void doBuildTemplate(RunData data, Context context)
			throws Exception {

		// Retrieve the form tool that has validated the input
		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		SecurityTool security = (SecurityTool) context
				.get(SecurityTool.DEFAULT_TOOL_NAME);

		GroupManager groupManager;
		String groupId;

		groupManager = security.getGroupManager();

		// get the user name from the text box
		groupId = ((Field) (form.getFields().get("groupid"))).getValue();

		// righty o we need all the users
		context.put("groups", groupManager.getAllGroups());

		// if there has been a user chosen set up the group info
		if (!StringUtils.isEmpty(groupId)) {
			RoleManager roleManager;
			DynamicGroup group;
			
			roleManager = security.getRoleManager();
			group = (DynamicGroup) groupManager.getGroupById(new Long(groupId));
			context.put("selectedgroup", group);

			// put in the users groups
			context.put("allocatedroles", group.getRoles());

			// find the groups that are left
			context.put("availableroles", PermissionHelper.roleSetXOR(group
					.getRoles(), roleManager.getAllRoles()));
		}
	}
}