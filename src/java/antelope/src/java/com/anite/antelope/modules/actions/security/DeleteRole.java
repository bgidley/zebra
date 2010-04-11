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
package com.anite.antelope.modules.actions.security;

import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.SecureAction;
import com.anite.antelope.modules.tools.SecurityTool;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;

/**
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class DeleteRole extends SecureAction {

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.modules.actions.VelocitySecureAction#doPerform(org.apache.turbine.util.RunData,
	 *      org.apache.velocity.context.Context)
	 */
	public void doPerform(RunData data, Context context) throws Exception {
		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		SecurityTool security = (SecurityTool) context
				.get(SecurityTool.DEFAULT_TOOL_NAME);

		if (form.isAllValid()) {
			// Declare variables
			RoleManager roleManager;			
			DynamicModelManager modelManager;
			FieldMap fieldMap;
			Field roleField;
			DynamicRole role;

			roleManager = security.getRoleManager();
			modelManager = (DynamicModelManager) security.getModelManager();
			

			fieldMap = form.getFields();
			roleField = (Field) fieldMap.get("allocatedroles");
			role = (DynamicRole) roleManager.getRoleById(Long
					.valueOf(roleField.getValue()));

			modelManager.revokeAll(role);
			roleManager.removeRole(role);
			// need to remove the username from the username from
			// the data so it isnt tried to be selected in the screen class
			roleField.setValue("");
		}
	}
}

