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

package com.anite.antelope.modules.screens;

import org.apache.turbine.modules.screens.VelocitySecureScreen;
import org.apache.turbine.services.velocity.TurbineVelocity;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.tools.SecurityTool;

/**
 * A general secure screen that implements the security needed for any secure
 * screen in the system. A screen which extends this class will not be able to
 * be viewed anonymous users.
 * 
 * @author <a href="mailto:michael.jones@anite.com">Michael.Jones </a>
 */
public abstract class SecureScreen extends VelocitySecureScreen {

    /**
     * Checks whether a user object matches the anonymous user pattern if the
     * user is anonymous then the user is returned to the login screen.
     * 
     * See org.apache.turbine.services.security.BaseSecurityService
     * 
     * @param data Turbine information.
     * @return True if the user is authorized to access the screen.
     * @exception Exception,
     *                a generic exception.
     */
    protected boolean isAuthorized(RunData data) throws Exception {

        Context context = TurbineVelocity.getContext(data);
        SecurityTool security = (SecurityTool) context
                .get(SecurityTool.DEFAULT_TOOL_NAME);

        // Either just null, the name is null or the name is the empty string
        // then the user is annonymous and needs to login
        if (security.isAnonUser(data)) {
            data.setScreenTemplate("Login.vm");
            return false;
        }
        return true;
    }
}