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

import org.apache.commons.lang.StringUtils;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
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
public class SelectGroup extends SecureAction {

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.modules.screens.VelocitySecureScreen#doBuildTemplate(org.apache.turbine.util.RunData,
	 *      org.apache.velocity.context.Context)
	 */
	public void doPerform(RunData data, Context context)
			{
		FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
		SecurityTool security = (SecurityTool) context
				.get(SecurityTool.DEFAULT_TOOL_NAME);

		if (form.isAllValid()) {
			GroupManager groupManager;
			FieldMap fieldMap;
			Field groupIdField;
			DynamicGroup group;

			groupManager = security.getGroupManager();
			fieldMap = form.getFields();
			groupIdField = (Field) fieldMap.get("groupid");

			if (!StringUtils.isEmpty(groupIdField.getValue())) {
				
				try {
					group = (DynamicGroup) groupManager.getGroupById(Long
							.valueOf(groupIdField.getValue()));
					context.put("selectedgroup", group);
				} catch (Exception e) {
					groupIdField.addMessage("Thats not a group!");
					data.setScreenTemplate("security,Groups.vm");										
				}					
			} else {
				groupIdField.addMessage("Please select a group!");
				data.setScreenTemplate("security,Groups.vm");
			}
		}
	}
}