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
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.SecureScreen;
import com.anite.antelope.modules.tools.SecurityTool;
import com.anite.antelope.utils.PermissionHelper;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 */
public class PermissionMaintenance extends SecureScreen {

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.modules.screens.VelocityScreen#doBuildTemplate(org.apache.turbine.util.RunData,
	 *      org.apache.velocity.context.Context)
	 */
	protected void doBuildTemplate(RunData data, Context context)
			throws Exception {
		//
		FormTool form;
		SecurityTool security;
		GroupManager groupManager;
		RoleManager roleManager;
		PermissionManager permissionManager;
		Field group;

		// Get the tools
		form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		security = (SecurityTool) context.get(SecurityTool.DEFAULT_TOOL_NAME);
		// populate the managers
		groupManager = security.getGroupManager();
		roleManager = security.getRoleManager();
		permissionManager = security.getPermissionManager();

		// the groups should alwasy be populated
		context.put("groups", groupManager.getAllGroups());

		group = (Field) form.getFields().get("groupid");

		// if a group has been selected populated the roles
		if (!StringUtils.isEmpty(group.getValue())) {
			DynamicGroup dynGroup;
			RoleSet rs;
			Field role;

			// get the group from the id
			dynGroup = (DynamicGroup) groupManager.getGroupById(Long.valueOf(group
					.getValue()));

			rs = dynGroup.getRoles();

			// make the selected group available
			context.put("selectedgroup", dynGroup);
			context.put("allocatedroles", rs);
			context.put("availableroles", PermissionHelper.roleSetXOR(rs,
					roleManager.getAllRoles()));

			role = (Field) form.getFields().get("allocatedroles");

			// if a role has been selected populate the permissions
			if (!StringUtils.isEmpty(role.getValue())) {
				DynamicRole dynRole;
				PermissionSet ps;

				dynRole = (DynamicRole) roleManager.getRoleById(new Long(role
						.getValue()));

				ps = dynRole.getPermissions();

				context.put("selectedrole", dynRole);
				context.put("allocatedperms", ps);
				context.put("availableperms", PermissionHelper
						.permissionSetXOR(ps, permissionManager
								.getAllPermissions()));

			
			}
		}
	}
}