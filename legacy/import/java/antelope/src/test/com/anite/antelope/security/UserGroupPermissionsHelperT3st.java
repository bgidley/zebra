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

package com.anite.antelope.security;


import java.util.Calendar;

import junit.framework.TestCase;

import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

import com.anite.antelope.TurbineTestCase;

/**
 * @author Ben.Gidley
 */
public class UserGroupPermissionsHelperT3st extends TestCase {

    private String groupName = "z12f9";
    private String userName = "borrisjohnson";

    private UserGroupPermissionsHelper helper;

    /* (non-Javadoc)
     * @see junit.framework.TestCase#setUp()
     */
    protected void setUp() throws Exception {
        TurbineTestCase.initialiseTurbine();

        helper = UserGroupPermissionsHelper.getInstance();
    }

    public void testCreateGroup() throws Exception {

        groupName = groupName + Calendar.getInstance().getTimeInMillis();
        
        DynamicGroup group = (DynamicGroup) helper.createOrFetchGroup(groupName);
        
        assertTrue(helper.getGroupManager().checkExists(groupName));
        assertTrue(helper.getRoleManager().checkExists(groupName));
        assertTrue(helper.getPermissionManager().checkExists(groupName));
        
        RoleSet roles = group.getRoles();
        assertTrue(roles.containsName(groupName));
        DynamicRole role = (DynamicRole) roles.getByName(groupName);
        assertTrue(role.getPermissions().containsName(groupName));
        
        // This time it should load it
        DynamicGroup groupMk2 = (DynamicGroup) helper.createOrFetchGroup(groupName);
        assertEquals(groupMk2.getId(), group.getId());
    }
    
    public void testCreateUser() throws Exception{
        userName = userName + Calendar.getInstance().getTimeInMillis();
        
        DynamicUser user = (DynamicUser) helper.createUser(userName, "rabbit");
        
        assertTrue(helper.getUserManager().checkExists(userName));
        assertTrue(helper.getGroupManager().checkExists(userName));
        assertTrue(helper.getRoleManager().checkExists(userName));
        assertTrue(helper.getPermissionManager().checkExists(userName));
        
        DynamicAccessControlList acl = (DynamicAccessControlList) helper.getUserManager().getACL(user);
        assertTrue(acl.hasPermission(userName));
        
        try {
            DynamicUser userMk2 = (DynamicUser) helper.createUser(userName, "rabbit");
        } catch (EntityExistsException e) {
            //PASS
            return;
        } catch (DataBackendException e) {
            fail();
        } catch (UnknownEntityException e) {
            fail();
        }
        fail();
    }
    
    
}