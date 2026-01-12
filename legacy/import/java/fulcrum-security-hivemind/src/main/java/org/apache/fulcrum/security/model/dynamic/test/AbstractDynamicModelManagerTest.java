package org.apache.fulcrum.security.model.dynamic.test;

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

import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

import org.apache.fulcrum.security.AbstractSecurityServiceTest;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.fulcrum.security.util.UserSet;

/**
 * @author Eric Pugh
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley </a>
 *  
 */
public abstract class AbstractDynamicModelManagerTest extends AbstractSecurityServiceTest {
    private static final String ONLY_BORRIS_PERMISSION = "ONLY_BORRIS_PERMISSION";

    private static final String ONLY_BORRIS_GROUP = "ONLY_BORRIS_GROUP";

    private static final String ONLY_BORRIS_ROLE = "ONLY BORRIS ROLE";

    private static final String USERNAME_SAM = "sam1";

    private static final String USERNAME_BORRIS = "borris1";

    private DynamicModelManager dynamicModelManager;

    public void setUp() throws Exception {
        super.setUp();
        this.dynamicModelManager = (DynamicModelManager) getModelManager();
    }

    public void testGrantRolePermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance();
        permission.setName("ANSWER_PHONE");
        getPermissionManager().addPermission(permission);
        Role role = getRoleManager().getRoleInstance("RECEPTIONIST");
        getRoleManager().addRole(role);
        getDynamicModelManager().grant(role, permission);
        role = getRoleManager().getRoleById(role.getId());
        PermissionSet permissions = ((DynamicRole) role).getPermissions();
        assertEquals(1, permissions.size());
        assertTrue(((DynamicRole) role).getPermissions().contains(permission));
    }

    public void testRevokeRolePermission() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance();
        permission.setName("ANSWER_FAX");
        getPermissionManager().addPermission(permission);
        Role role = getRoleManager().getRoleInstance("SECRETARY");
        getRoleManager().addRole(role);
        getDynamicModelManager().grant(role, permission);
        role = getRoleManager().getRoleById(role.getId());
        PermissionSet permissions = ((DynamicRole) role).getPermissions();
        assertEquals(1, permissions.size());
        getDynamicModelManager().revoke(role, permission);
        role = getRoleManager().getRoleById(role.getId());
        permissions = ((DynamicRole) role).getPermissions();
        assertEquals(0, permissions.size());
        assertFalse(((DynamicRole) role).getPermissions().contains(permission));
    }

    public void testRevokeAllRole() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance();
        Permission permission2 = getPermissionManager().getPermissionInstance();
        permission.setName("SEND_SPAM");
        permission2.setName("ANSWER_EMAIL");
        getPermissionManager().addPermission(permission);
        getPermissionManager().addPermission(permission2);
        Role role = getRoleManager().getRoleInstance("HELPER");
        getRoleManager().addRole(role);
        getDynamicModelManager().grant(role, permission);
        getDynamicModelManager().grant(role, permission2);
        role = getRoleManager().getRoleById(role.getId());
        PermissionSet permissions = ((DynamicRole) role).getPermissions();
        assertEquals(2, permissions.size());
        getDynamicModelManager().revokeAll(role);
        role = getRoleManager().getRoleById(role.getId());
        permissions = ((DynamicRole) role).getPermissions();
        assertEquals(0, permissions.size());
    }

    public void testRevokeAllGroup() throws Exception {
        Permission permission = getPermissionManager().getPermissionInstance();
        Permission permission2 = getPermissionManager().getPermissionInstance();
        permission.setName("SEND_SPAM2");
        permission2.setName("ANSWER_EMAIL2");
        getPermissionManager().addPermission(permission);
        getPermissionManager().addPermission(permission2);
        Role role = getRoleManager().getRoleInstance("HELPER2");
        getRoleManager().addRole(role);
        getDynamicModelManager().grant(role, permission);
        getDynamicModelManager().grant(role, permission2);
        role = getRoleManager().getRoleById(role.getId());
        PermissionSet permissions = ((DynamicRole) role).getPermissions();
        assertEquals(2, permissions.size());
        getDynamicModelManager().revokeAll(role);
        role = getRoleManager().getRoleById(role.getId());
        permissions = ((DynamicRole) role).getPermissions();
        assertEquals(0, permissions.size());
    }

    public void testRevokeAllUser() throws Exception {
        Group group = getGroupManager().getGroupInstance();
        group.setName("TEST_REVOKEALLUSER_GROUP");
        getGroupManager().addGroup(group);
        Role role = getRoleManager().getRoleInstance();
        role.setName("TEST_REVOKEALLUSER_ROLE");
        getRoleManager().addRole(role);
        User user = getUserManager().getUserInstance("calvin");
        getUserManager().addUser(user, "calvin");
        getDynamicModelManager().grant(user, group);
        getDynamicModelManager().grant(group, role);
        group = getGroupManager().getGroupById(group.getId());
        RoleSet roles = ((DynamicGroup) group).getRoles();
        assertEquals(1, roles.size());
        UserSet users = ((DynamicGroup) group).getUsers();
        assertEquals(1, users.size());

        getDynamicModelManager().revokeAll(group);
        assertEquals(0, ((DynamicGroup) group).getUsers().size());
        role = getRoleManager().getRoleByName("TEST_REVOKEALLUSER_ROLE");

        assertFalse(((DynamicRole) role).getGroups().contains(group));

    }

    public void testRevokeAllPermission() throws Exception {
        Role role = getRoleManager().getRoleInstance();
        Role role2 = getRoleManager().getRoleInstance();
        role.setName("SEND_SPAM");
        role2.setName("ANSWER_EMAIL");
        getRoleManager().addRole(role);
        getRoleManager().addRole(role2);
        Permission permission = getPermissionManager().getPermissionInstance("HELPER");
        getPermissionManager().addPermission(permission);
        getDynamicModelManager().grant(role, permission);
        getDynamicModelManager().grant(role2, permission);
        permission = getPermissionManager().getPermissionById(permission.getId());
        RoleSet roles = ((DynamicPermission) permission).getRoles();
        assertEquals(2, roles.size());
        getDynamicModelManager().revokeAll(permission);
        permission = getPermissionManager().getPermissionById(permission.getId());
        roles = ((DynamicPermission) permission).getRoles();
        assertEquals(0, roles.size());
    }

    public void testGrantUserGroup() throws Exception {
        Group group = getGroupManager().getGroupInstance();
        group.setName("TEST_GROUP");
        getGroupManager().addGroup(group);
        User user = getUserManager().getUserInstance("Clint");
        getUserManager().addUser(user, "clint");
        getDynamicModelManager().grant(user, group);
        assertTrue(((DynamicUser) user).getGroups().contains(group));
        assertTrue(((DynamicGroup) group).getUsers().contains(user));
    }

    public void testRevokeUserGroup() throws Exception {
        Group group = getGroupManager().getGroupInstance();
        group.setName("TEST_REVOKE");
        getGroupManager().addGroup(group);
        User user = getUserManager().getUserInstance("Lima");
        getUserManager().addUser(user, "pet");
        getDynamicModelManager().revoke(user, group);
        assertFalse(((DynamicUser) user).getGroups().contains(group));
        assertFalse(((DynamicGroup) group).getUsers().contains(user));
        user = getUserManager().getUser("Lima");
        assertFalse(((DynamicUser) user).getGroups().contains(group));
    }

    public void testGrantGroupRole() throws Exception {
        Role role = getRoleManager().getRoleInstance();
        role.setName("TEST_PERMISSION");
        getRoleManager().addRole(role);
        Group group = getGroupManager().getGroupInstance("TEST_GROUP2");
        getGroupManager().addGroup(group);
        getDynamicModelManager().grant(group, role);
        group = getGroupManager().getGroupByName("TEST_GROUP2");
        assertTrue(((DynamicGroup) group).getRoles().contains(role));
        assertTrue(((DynamicRole) role).getGroups().contains(group));

    }

    public void testRevokeGroupRole() throws Exception {
        Role role = getRoleManager().getRoleInstance();
        role.setName("TEST_PERMISSION2");
        getRoleManager().addRole(role);
        Group group = getGroupManager().getGroupInstance("Lima2");
        getGroupManager().addGroup(group);
        getDynamicModelManager().grant(group, role);
        getDynamicModelManager().revoke(group, role);
        group = getGroupManager().getGroupByName("Lima2");
        assertFalse(((DynamicGroup) group).getRoles().contains(role));
        assertFalse(((DynamicRole) role).getGroups().contains(group));
    }

    @SuppressWarnings("unchecked")
	public void testRetrieveingUsersByGroup() throws Exception {
        User user = getUserManager().getUserInstance("Joe3");
        getUserManager().addUser(user, "mc");
        String GROUP_NAME = "oddbug2";
        Group group = null;

        try {
            group = getGroupManager().getGroupByName("");
        } catch (UnknownEntityException uue) {
            group = getGroupManager().getGroupInstance(GROUP_NAME);
            getGroupManager().addGroup(group);
        }
        assertNotNull(group);
        user = null;

        user = getUserManager().getUser("joe3");
        getDynamicModelManager().grant(user, group);
        assertTrue(((DynamicGroup) group).getUsers().contains(user));
        group = getGroupManager().getGroupByName(GROUP_NAME);
        Set users = ((DynamicGroup) group).getUsers();
        int size = users.size();
        assertEquals(1, size);
        // assertTrue("Check class:" + users.getClass().getName(),users
        // instanceof UserSet);
        boolean found = false;
        Set newSet = new HashSet();
        for (Iterator i = users.iterator(); i.hasNext();) {
            User u = (User) i.next();
            if (u.equals(user)) {
                found = true;
                newSet.add(u);
            }
        }
        assertTrue(found);
        assertTrue(users.contains(user));
    }

    public void testAddRemoveDelegate() throws Exception {
        DynamicUser borris = (DynamicUser) getUserManager().getUserInstance(USERNAME_BORRIS);
        getUserManager().addUser(borris, "mc");
        DynamicUser sam = (DynamicUser) getUserManager().getUserInstance(USERNAME_SAM);
        getUserManager().addUser(sam, "mc");
        getDynamicModelManager().addDelegate(borris, sam);
        assertTrue(borris.getDelegatees().contains(sam));
        assertTrue(sam.getDelegators().contains(borris));

        DynamicUser borrisLoaded = (DynamicUser) getUserManager().getUser(USERNAME_BORRIS);
        DynamicUser samLoaded = (DynamicUser) getUserManager().getUser(USERNAME_SAM);
        assertTrue(borrisLoaded.getDelegatees().contains(samLoaded));
        assertTrue(samLoaded.getDelegators().contains(borrisLoaded));

        // Now grant borris some permissions and check sam has them
        Group group = getGroupManager().getGroupInstance();
        group.setName(ONLY_BORRIS_GROUP);
        getGroupManager().addGroup(group);
        Role role = getRoleManager().getRoleInstance();
        role.setName(ONLY_BORRIS_ROLE);
        getRoleManager().addRole(role);
        Permission permission = getPermissionManager().getPermissionInstance();
        permission.setName(ONLY_BORRIS_PERMISSION);
        getPermissionManager().addPermission(permission);

        getDynamicModelManager().grant(role, permission);
        getDynamicModelManager().grant(group, role);
        getDynamicModelManager().grant(borris, group);

        DynamicAccessControlList acl = (DynamicAccessControlList) getUserManager().getACL(sam);
        assertTrue(acl.hasPermission(permission));
        assertTrue(acl.hasRole(role));

        // Now just to be silly make it recursive and check permissions work
        getDynamicModelManager().addDelegate(sam, borris);
        acl = (DynamicAccessControlList) getUserManager().getACL(sam);
        assertTrue(acl.hasPermission(permission));
        assertTrue(acl.hasRole(role));

        getDynamicModelManager().removeDelegate(borris, sam);
        assertFalse(borris.getDelegatees().contains(sam));
        assertFalse(sam.getDelegators().contains(borris));

        borrisLoaded = (DynamicUser) getUserManager().getUser(USERNAME_BORRIS);
        samLoaded = (DynamicUser) getUserManager().getUser(USERNAME_BORRIS);
        assertFalse(borrisLoaded.getDelegatees().contains(samLoaded));
        assertFalse(samLoaded.getDelegators().contains(borrisLoaded));

        boolean thrown = false;
        try {
            getDynamicModelManager().removeDelegate(borris, sam);
        } catch (DataBackendException e) {
            throw e;
        } catch (UnknownEntityException e) {
            thrown = true;
        }
        assertTrue(thrown);
    }

    public DynamicModelManager getDynamicModelManager() {
        return dynamicModelManager;
    }

}