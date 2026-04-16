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
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.SecureAction;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 */
public class ChangeUserGroup extends SecureAction {

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
            UserManager usermanager;
            GroupManager groupManager;
            DynamicModelManager modelManager;

            DynamicUser user;
            DynamicGroup group;
            FieldMap fieldMap;
            Field usernameField;
            Field groupsField;
            String[] groupIds;

            // get the security service and manager to do the work with
            securityService = AvalonServiceHelper.instance()
                    .getSecurityService();
            usermanager = securityService.getUserManager();
            groupManager = securityService.getGroupManager();
            modelManager = (DynamicModelManager) securityService
                    .getModelManager();

            fieldMap = form.getFields();

            // get the user name from the combo box
            usernameField = (Field) fieldMap.get("username");

            user = (DynamicUser) usermanager.getUser(usernameField.getValue());

            // do this if removegroup has been selected
            // TODO This is going to be changed as the validation should return a 
            // button field with a is clicked method
            if (!StringUtils.isEmpty(((Field) fieldMap.get("doremovegroup"))
                    .getValue())) {
                // get the allocated groups and store them in a
                // string array
                groupsField = (Field) fieldMap.get("allocatedgroups");
                groupIds = groupsField.getValues();

                // check that a group has been selected
                if (groupIds.length > 0) {
                    for (int i = 0; i < groupIds.length; i++) {
                        group = (DynamicGroup) groupManager
                                .getGroupById(new Long(groupIds[i]));
                        modelManager.revoke(user, group);

                    }
                } else
                    data.setMessage("You must select a role to remove.");
            } else if (!StringUtils
                    .isEmpty(((Field) fieldMap.get("doaddgroup")).getValue())) {
                // get the allocated groups and store them in a
                // string array
                groupsField = (Field) fieldMap.get("availablegroups");
                groupIds = groupsField.getValues();

                // check that a group has been selected
                if (groupIds.length > 0) {
                    for (int i = 0; i < groupIds.length; i++) {
                        group = (DynamicGroup) groupManager
                                .getGroupById(new Long(groupIds[i]));
                        modelManager.grant(user, group);
                    }
                } else {
                    data.setMessage("You must select a role to add.");
                }
            }
        } // end of if form valid  
        data.setScreenTemplate("security,Users.vm");
    }// end of doPerform
}