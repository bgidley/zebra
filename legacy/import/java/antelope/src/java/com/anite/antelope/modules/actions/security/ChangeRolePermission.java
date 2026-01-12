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
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
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
public class ChangeRolePermission extends SecureAction {

    private final static Log log = LogFactory
            .getLog(ChangeRolePermission.class);

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
            RoleManager roleManager;
            PermissionManager permManager;
            DynamicModelManager modelManager;

            DynamicRole role;
            DynamicPermission perm;
            FieldMap fieldMap;
            Field roleNameField;
            Field permsField;
            String[] permIds;

            // get the security service and managers to do the work with
            securityService = AvalonServiceHelper.instance()
                    .getSecurityService();
            roleManager = securityService.getRoleManager();
            permManager = securityService.getPermissionManager();
            modelManager = (DynamicModelManager) securityService
                    .getModelManager();
            fieldMap = form.getFields();

            // find the selected role
            roleNameField = (Field) fieldMap.get("allocatedroles");
            role = (DynamicRole) roleManager.getRoleById(new Long(roleNameField
                    .getValue()));

            // do this if remove permission has been selected
            if (!StringUtils.isEmpty(((Field) fieldMap.get("doremoveperm"))
                    .getValue())) {
                // get the allocated permissions and store them in an array
                permsField = (Field) fieldMap.get("allocatedperms");
                permIds = permsField.getValues();

                // loops roudn the selected permissions
                if (permIds.length > 0) {
                    for (int i = 0; i < permIds.length; i++) {
                        perm = (DynamicPermission) permManager
                                .getPermissionById(new Long(permIds[i]));
                        modelManager.revoke(role, perm);
                        role.removePermission(perm);
                    }
                } else {
                    data.setMessage("You must select a permission to remove.");
                }
            } else if (!StringUtils.isEmpty(((Field) fieldMap.get("doaddperm"))
                    .getValue())) {
                // get the allocated groups and store them in a
                // string array
                permsField = (Field) fieldMap.get("availableperms");
                permIds = permsField.getValues();

                // check that a group has been selected
                if (permIds.length > 0) {
                    for (int i = 0; i < permIds.length; i++) {
                        perm = (DynamicPermission) permManager
                                .getPermissionById(new Long(permIds[i]));
                        modelManager.grant(role, perm);
                    }
                } else {
                    data.setMessage("You must select a permission to add.");
                }
            }
        } // end of if form valid
    }// end of doPerform
}