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
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
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
public class ChangeGroupRole extends SecureAction {

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.modules.actions.VelocitySecureAction#doPerform(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context)
     */
    public void doPerform(RunData data, Context context) throws Exception {
        // Retrieve the form tool that has validated the input
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            // Declare variables
            SecurityService securityService;
            GroupManager groupManager;
            RoleManager roleManager;
            DynamicModelManager modelManager;

            DynamicGroup group;
            DynamicRole role;
            FieldMap fieldMap;
            Field groupIdField;
            Field rolesField;
            String[] roleIds;

            // get the security service and manager to do the work with
            securityService = AvalonServiceHelper.instance()
                    .getSecurityService();

            groupManager = securityService.getGroupManager();
            roleManager = securityService.getRoleManager();
            modelManager = (DynamicModelManager) securityService
                    .getModelManager();

            fieldMap = form.getFields();

            // get the group name from the combo box
            groupIdField = (Field) fieldMap.get("groupid");

            group = (DynamicGroup) groupManager.getGroupById(new Long(
                    groupIdField.getValue()));

            // do this if removegroup has been selected
            // TODO This is going to be changed as the validation should return
            // a button field with a is clicked method
            if (!StringUtils.isEmpty(((Field) fieldMap.get("doremoverole"))
                    .getValue())) {
                // get the allocated groups and store them in a
                // string array
                rolesField = (Field) fieldMap.get("allocatedroles");
                roleIds = rolesField.getValues();

                // check that a group has been selected
                if (roleIds.length > 0) {
                    for (int i = 0; i < roleIds.length; i++) {
                        role = (DynamicRole) roleManager.getRoleById(new Long(
                                roleIds[i]));
                        modelManager.revoke(group, role);
                    }
                    // remove the values so the permissions for the removed
                    // roles arent displayed in the screen
                    rolesField.setValue("");
                } else {
                    data.setMessage("You must select a role to remove.");
                }
            } else if (!StringUtils.isEmpty(((Field) fieldMap.get("doaddrole"))
                    .getValue())) {
                // get the allocated groups and store them in a
                // string array
                rolesField = (Field) fieldMap.get("availableroles");
                roleIds = rolesField.getValues();

                // check that a group has been selected
                if (roleIds.length > 0) {
                    for (int i = 0; i < roleIds.length; i++) {
                        role = (DynamicRole) roleManager.getRoleById(new Long(
                                roleIds[i]));
                        modelManager.grant(group, role);
                    }
                } else{
                    data.setMessage("You must select a group to remove.");}
            }
        } // end of if form valid
        // TODO should the screen be decided in the action? I think it should so its prob
        // best not to pass in with the link.. but this is a common action.. so there 
        // needs to be multiple entery point to it so
        //data.setScreenTemplate("security,Groups.vm");
    }// end of doPerform
}