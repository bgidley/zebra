/*
 * Copyright 2004 Anite - Central Government Division
 *    http://www.anite.com/publicsector
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.anite.antelope.modules.actions;

import org.apache.fulcrum.security.adapter.turbine.UserAdapter;
import org.apache.turbine.modules.actions.VelocityAction;
import org.apache.turbine.om.security.User;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;

/**
 * @author Michael.Jones
 */
public class LogoutUser extends VelocityAction {
    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.modules.actions.VelocityAction#doPerform(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context)
     */
    public void doPerform(RunData data, Context context) throws Exception {

        User anonUser = new UserAdapter(AvalonServiceHelper.instance()
                .getSecurityService().getUserManager().getUserInstance());

        // This will cause the acl to be removed from the session in
        // the Turbine servlet code.
        data.setACL(null);

        // Retrieve an anonymous user.
        data.setUser(anonUser);
        data.save();
        
        // tell the user locator
        UserLocator.setLoggedInUser(null);
    }
}