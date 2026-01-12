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
package com.anite.antelope;

import org.apache.fulcrum.security.SecurityService;



/**
 * This class sets up the managers for the AbstractCreateUsers
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class HibernateCreateUsersTest extends AbstractCreateUsersTest {

    /**
     * @param arg0
     */
    public HibernateCreateUsersTest(String arg0) {
        super(arg0);
    }

    public void setUp() {
        try {
            this.setRoleFileName(null);
            this.setConfigurationFileName("src/test/DynamicHibernate.xml");
            //HibernateService hibernateService = (HibernateService) lookup(HibernateService.ROLE);
            
            securityService = (SecurityService) lookup(SecurityService.ROLE);
            userManager = securityService.getUserManager();
            groupManager = securityService.getGroupManager();
            roleManager = securityService.getRoleManager();
            permissionManager = securityService.getPermissionManager();
            
        } catch (Exception e) {
            fail(e.toString());
        }
    }

    public void tearDown() {        
        userManager = null;
        groupManager = null;
        roleManager = null;
        permissionManager = null;
        securityService = null;
    }

 

}