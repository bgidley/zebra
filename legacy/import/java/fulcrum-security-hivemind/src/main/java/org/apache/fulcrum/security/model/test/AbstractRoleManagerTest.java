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
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * @author Eric Pugh
 *
 * To change the template for this generated type comment go to
 * Window>Preferences>Java>Code Generation>Code and Comments
 */
public abstract class AbstractRoleManagerTest extends AbstractSecurityServiceTest {

    /*
     * Class to test for Role getRoleInstance()
     */
    public void testGetRoleInstance() throws Exception {
        Role role = getRoleManager().getRoleInstance();
        assertNotNull(role);
        assertTrue(role.getName() == null);
    }

    /*
     * Class to test for Role getRoleInstance(String)
     */
    public void testGetRoleInstanceString() throws Exception {
        Role role = getRoleManager().getRoleInstance("DOG_CATCHER");
        assertEquals("dog_catcher", role.getName());
    }

    public void testGetRoleByName() throws Exception {
        Role role = getRoleManager().getRoleInstance("DOG_CATCHERd");
        getRoleManager().addRole(role);
        Role role2 = getRoleManager().getRoleByName("DOG_CATCHERd");
        assertEquals(role.getName(), role2.getName());
    }

    public void testGetRoleById() throws Exception {
        Role role = getRoleManager().getRoleInstance("CLEAN_KENNEL_A");
        getRoleManager().addRole(role);
        Role role2 = getRoleManager().getRoleById(role.getId());
        assertEquals(role.getName(), role2.getName());
    }

    public void testRenameRole() throws Exception {
        Role role = getRoleManager().getRoleInstance("CLEAN_KENNEL_X");
        getRoleManager().addRole(role);
        int size = getRoleManager().getAllRoles().size();
        getRoleManager().renameRole(role, "CLEAN_GROOMING_ROOM");
        Role role2 = getRoleManager().getRoleById(role.getId());
        assertEquals("clean_grooming_room", role2.getName());
        assertEquals(size, getRoleManager().getAllRoles().size());
    }

    public void testGetAllRoles() throws Exception {
        int size = getRoleManager().getAllRoles().size();
        Role role = getRoleManager().getRoleInstance("CLEAN_KENNEL_J");
        getRoleManager().addRole(role);
        RoleSet roleSet = getRoleManager().getAllRoles();
        assertEquals(size + 1, roleSet.size());
    }

    public void testAddRole() throws Exception {
        Role role = getRoleManager().getRoleInstance("DOG_NAPPER");
        assertNull(role.getId());
        getRoleManager().addRole(role);
        assertNotNull(role.getId());
        assertNotNull(getRoleManager().getRoleById(role.getId()));
    }

    public void testRemoveRole() throws Exception {
        Role role = getRoleManager().getRoleInstance("CLEAN_KENNEL_K");
        getRoleManager().addRole(role);
        int size = getRoleManager().getAllRoles().size();
        getRoleManager().removeRole(role);
        try {
            getRoleManager().getRoleById(role.getId());
            fail("Should have thrown UEE");
        } catch (UnknownEntityException uee) {
            //good
        }
        assertEquals(size - 1, getRoleManager().getAllRoles().size());
    }

	public void testDisableRole() throws Exception {
        Role role = getRoleManager().getRoleInstance("CLEAN_KENNEL_L");
        getRoleManager().addRole(role);
        getRoleManager().disableRole(role);
		try {
			getRoleManager().getRoleByName(role.getName());
			fail("Should have thrown EntityDisabledException");
		} catch (EntityDisabledException ede) {
			// brilliant!
		}
		
		try {
			getRoleManager().addRole(role);
			fail("Should have thrown EntityExistsException");
		} catch (EntityExistsException eee) {
			// brilliant!
		}
	}
    
    public void testCheckExists() throws Exception {
        Role role = getRoleManager().getRoleInstance("GREET_PEOPLE");
        getRoleManager().addRole(role);
        assertTrue(getRoleManager().checkExists(role));
        Role role2 = getRoleManager().getRoleInstance("WALK_DOGS");
        assertFalse(getRoleManager().checkExists(role2));
    }

    public void testCheckExistsWithString() throws Exception {
        Role role = getRoleManager().getRoleInstance("GREET_PEOPLE2");
        getRoleManager().addRole(role);
        assertTrue(getRoleManager().checkExists(role.getName()));
        Role role2 = getRoleManager().getRoleInstance("WALK_DOGS2");
        assertFalse(getRoleManager().checkExists(role2.getName()));
    }

    /*
     * Class to test for boolean checkExists(string)
     */
    public void testAddRoleTwiceFails() throws Exception {
        Role role = getRoleManager().getRoleInstance("EATLUNCH");
        getRoleManager().addRole(role);
        assertTrue(getRoleManager().checkExists(role.getName()));
        Role role2 = getRoleManager().getRoleInstance("EATLUNCH");
        try {
            getRoleManager().addRole(role2);
        } catch (EntityExistsException uee) {
            //good
        }
    }
}
