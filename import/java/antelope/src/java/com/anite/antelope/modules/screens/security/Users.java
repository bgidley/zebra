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
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.SecureScreen;
import com.anite.antelope.modules.tools.SecurityTool;
import com.anite.antelope.utils.PermissionHelper;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Michael.Jones
 */
public class Users extends SecureScreen {

    /**
     * Populates the select boxes for the users maintenace screen
     */
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {
        // Retrieve the form tool that has validated the input
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        SecurityTool security = (SecurityTool) context.get(SecurityTool.DEFAULT_TOOL_NAME);
        
        UserManager usermanager = security.getUserManager();
        GroupManager groupManager = security.getGroupManager();
        String userName;
        DynamicUser user;
        
        // get the user name from the text box
        userName = ((Field)(form.getFields().get("username"))).getValue();

        // righty o we need all the users
        context.put("users", usermanager.getAllUsers());

        // if there has been a user chosen set up the group info
        if (!StringUtils.isEmpty(userName)) {
            user = (DynamicUser) usermanager.getUser(userName);
            context.put("selectedUser", user);

            // put in the users groups
            context.put("userGroups", user.getGroups());

            // find the groups that are left
            context.put("availableGroups", PermissionHelper.groupSetXOR(user
                    .getGroups(), groupManager.getAllGroups()));
        }
    }
}