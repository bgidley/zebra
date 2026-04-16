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

package com.anite.antelope.utils;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.fulcrum.security.SecurityService;
import org.apache.turbine.services.InitializationException;
import org.apache.turbine.services.TurbineServices;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;

/**
 * @author Michael.Jones
 */
public class AvalonServiceHelper {

    private static AvalonServiceHelper _instance;

    public static AvalonServiceHelper instance() {
        if (_instance == null) {
            _instance = new AvalonServiceHelper();
        }
        return _instance;
    }

    /**
     * This method returns the Fulcrum secturit service from avalon
     * 
     * @return @throws
     *         InitializationException
     */
    public SecurityService getSecurityService() throws InitializationException {
        SecurityService securityService;
        AvalonComponentService acs;

        acs = (AvalonComponentService) TurbineServices.getInstance()
                .getService(AvalonComponentService.SERVICE_NAME);
        try {
            securityService = (SecurityService) acs
                    .lookup(SecurityService.ROLE);
        } catch (ComponentException ce) {
            throw new InitializationException(
                    "Could not retrieve Avalon Security Service:"
                            + ce.getMessage(), ce);
        }
        return securityService;
    }

}