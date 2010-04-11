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

import org.apache.fulcrum.security.PermissionManager;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.SecureScreen;
import com.anite.antelope.modules.tools.SecurityTool;


/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class Permissions extends SecureScreen {

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.modules.screens.VelocitySecureScreen#doBuildTemplate(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context)
     */
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {
        
        // Get the managers from the tool
        SecurityTool security = (SecurityTool) context.get(SecurityTool.DEFAULT_TOOL_NAME);
        PermissionManager permissionManager = security.getPermissionManager();
        context.put("permissions", permissionManager.getAllPermissions());
    }
}