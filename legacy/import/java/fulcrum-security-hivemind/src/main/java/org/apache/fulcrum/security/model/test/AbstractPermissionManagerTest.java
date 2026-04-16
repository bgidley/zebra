package org.apache.fulcrum.security.model.test;

/*
 *  Copyright 2001-2004 The Apache Software Foundation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

import org.apache.fulcrum.security.AbstractSecurityServiceTest;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * @author Eric Pugh
 *
 * To change the template for this generated type comment go to
 * Window>Preferences>Java>Code Generation>Code and Comments
 */
public abstract class AbstractPermissionManagerTest extends AbstractSecurityServiceTest {

    /*
     * Class to test for Permission getPermissionInstance()
     */
    public void testGetPermissionInstance() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance();
        assertNotNull(permission);
        assertTrue(permission.getName() == null);
    }

    /*
     * Class to test for Permission getPermissionInstance(String)
     */
    public void testGetPermissionInstanceString() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CAN_TREAT_ANIMALS");
        assertEquals("can_treat_animals", permission.getName());
    }

    public void testGetPermissionByName() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CLEAN_KENNEL");
        getPermissionManager().addPermission(permission);
        Permission permission2 = getPermissionManager().getPermissionByName("CLEAN_KENNEL");
        assertEquals(permission.getName(), permission2.getName());
    }

    public void testGetPermissionById() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("ADMINSTER_DRUGS");
        getPermissionManager().addPermission(permission);
        Permission permission2 = getPermissionManager().getPermissionById(permission.getId());
        assertEquals(permission.getName(), permission2.getName());
    }

    public void testGetAllPermissions() throws Exception {
        int size = getPermissionManager().getAllPermissions().size();
        Permission permission = getPermissionManager().getPermissionInstance("WALK_DOGS");
        getPermissionManager().addPermission(permission);
        PermissionSet permissionSet = getPermissionManager().getAllPermissions();
        assertEquals(size + 1, permissionSet.size());
    }

    public void testRenamePermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CLEAN_FRONT_OFFICE");
        getPermissionManager().addPermission(permission);
        int size = getPermissionManager().getAllPermissions().size();
        getPermissionManager().renamePermission(permission, "CLEAN_GROOMING_ROOM");
        Permission permission2 = getPermissionManager().getPermissionById(permission.getId());
        assertEquals("CLEAN_GROOMING_ROOM".toLowerCase(), permission2.getName());
        assertEquals(size, getPermissionManager().getAllPermissions().size());
    }

    public void testRemovePermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CLEAN_CAT_HOUSE");
        getPermissionManager().addPermission(permission);
        getPermissionManager().removePermission(permission);
        try {
            permission = getPermissionManager().getPermissionById(permission.getId());
            fail("Should have thrown UnknownEntityException");
        } catch (UnknownEntityException uee) {
            //good
        }
    }
    
	public void testDisablePermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CLEAN_KENNEL_L");
        getPermissionManager().addPermission(permission);
        getPermissionManager().disablePermission(permission);
		try {
			getPermissionManager().getPermissionByName(permission.getName());
			fail("Should have thrown EntityDisabledException");
		} catch (EntityDisabledException ede) {
			// brilliant!
		}
		
		try {
			getPermissionManager().addPermission(permission);
			fail("Should have thrown EntityExistsException");
		} catch (EntityExistsException eee) {
			// brilliant!
		}
	}

    public void testAddPermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("CLEAN_BIG_KENNEL");
        assertNull(permission.getId());
        getPermissionManager().addPermission(permission);
        assertNotNull(permission.getId());
        permission = getPermissionManager().getPermissionById(permission.getId());
        assertNotNull(permission);
    }

    /*
     * Class to test for PermissionSet getPermissions(Role)
     */
    public void testGetPermissionsRole() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("GREET_PEOPLE");
        getPermissionManager().addPermission(permission);
        Permission permission2 = getPermissionManager().getPermissionInstance("ADMINISTER_DRUGS");
        getPermissionManager().addPermission(permission2);
        Role role = getRoleManager().getRoleInstance("VET_TECH");
        getRoleManager().addRole(role);
        ((DynamicModelManager) getModelManager()).grant(role, permission);
        PermissionSet permissions = ((DynamicRole) role).getPermissions();
        assertEquals(1, permissions.size());
        assertTrue(permissions.contains(permission));
        assertFalse(permissions.contains(permission2));
    }

    /*
     * Class to test for boolean checkExists(permission)
     */
    public void testCheckExistsPermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("OPEN_OFFICE");
        getPermissionManager().addPermission(permission);
        assertTrue(getPermissionManager().checkExists(permission));
        Permission permission2 = getPermissionManager().getPermissionInstance("CLOSE_OFFICE");
        assertFalse(getPermissionManager().checkExists(permission2));
    }

    /*
     * Class to test for boolean checkExists(string)
     */
    public void testCheckExistsPermissionWithString() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("OPEN_OFFICE2");
        getPermissionManager().addPermission(permission);
        assertTrue(getPermissionManager().checkExists(permission.getName()));
        Permission permission2 = getPermissionManager().getPermissionInstance("CLOSE_OFFICE2");
        assertFalse(getPermissionManager().checkExists(permission2.getName()));
    }

    /*
     * Class to test for boolean checkExists(string)
     */
    public void testAddPermissionTwiceFails() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance("EATLUNCH");
        getPermissionManager().addPermission(permission);
        assertTrue(getPermissionManager().checkExists(permission.getName()));
        Permission permission2 = getPermissionManager().getPermissionInstance("EATLUNCH");
        try {
            getPermissionManager().addPermission(permission2);
        } catch (EntityExistsException uee) {
            //good
        }
    }
}
