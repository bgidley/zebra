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
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.entity.Role;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.SecureAction;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class AddRole extends SecureAction {

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.modules.actions.VelocitySecureAction#doPerform(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context)
     */
    public void doPerform(RunData data, Context context) throws Exception {
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            // Declare variables
            SecurityService securityService;
            RoleManager roleManager;

            FieldMap fieldMap;
            Field roleField;

            // get the security service and manager to do the work with
            securityService = AvalonServiceHelper.instance()
                    .getSecurityService();
            roleManager = securityService.getRoleManager();

            fieldMap = form.getFields();

            roleField = (Field) fieldMap.get("rolename");

            // check the name hasnt already been taken before adding it
            if (!roleManager.checkExists(roleManager
                    .getRoleInstance(roleField.getValue()))) {
                Role role;
                role = roleManager.getRoleInstance(roleField.getValue());
                roleManager.addRole(role);
            } else {
                roleField.addMessage("\"" + roleField.getValue()
                        + "\"is alread a role name!");
                data.setScreenTemplate("security,AddRole.vm");
            }
        } else{
            data.setScreenTemplate("security,AddRole.vm");
        }
    }

}