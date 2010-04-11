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
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.User;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.SecureAction;
import com.anite.antelope.modules.tools.SecurityTool;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;

/**
 * This secure action adds new user to the system
 * 
 * @author Michael.Jones
 */
public class AddUser extends SecureAction {

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

            UserManager usermanager;

            FieldMap fieldMap;
            Field usernameField;
            Field passwordField, confPasswordField;

            usermanager = security.getUserManager();
            fieldMap = form.getFields();

            usernameField = (Field) fieldMap.get("username");

            // check the username isnt alreay used
            if (usermanager.checkExists(usernameField.getValue())) {
                usernameField.addMessage("Username already taken!");
                data.setScreenTemplate("security,AddUser.vm");
                return;
            }

            passwordField = (Field) fieldMap.get("password");
            confPasswordField = (Field) fieldMap.get("confpassword");

            // check the password match before adding the user
            if (StringUtils.equals(passwordField.getValue(), confPasswordField
                    .getValue())) {
                User user;
                user = usermanager.getUserInstance(usernameField.getValue());
                usermanager.addUser(user, passwordField.getValue());
            } else {
                passwordField.addMessage("Passwords dont match!");
                data.setScreenTemplate("security,AddUser.vm");
            }
        } else {
            data.setScreenTemplate("security,AddUser.vm");
        }
    }
}