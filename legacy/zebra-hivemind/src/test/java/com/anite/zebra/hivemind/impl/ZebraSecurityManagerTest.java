/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.impl;

import java.util.Iterator;
import java.util.List;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.ModelManager;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.hibernate.dynamic.model.HibernateDynamicUser;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

public class ZebraSecurityManagerTest extends TestCase {

    protected UserManager userManager;

    protected PermissionManager permissionManager;

    protected RoleManager roleManager;

    protected GroupManager groupManager;

    protected DynamicModelManager modelManager;

    private static final String FIRST_SCREEN = "First Screen";

    private static final String SECOND_SCREEN = "Second Screen";

    private static final String TEST_PERMISSION = "TestPermission";

    private static final String YES = "Yes";

    private Zebra zebra;

    HibernateDynamicUser adminUser;

    HibernateDynamicUser user;

    /*
     * @see TestCase#setUp()
     */
    protected void setUp() throws Exception {

        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);

        this.zebra = (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra", Zebra.class);

    }

    public void testGetService() {
        ZebraSecurity security = (ZebraSecurity) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraSecurity", ZebraSecurity.class);

        assertNotNull(security);
        assertNotNull(security.getPermissionManager());
    }

    /** 
     * Test getPermission test related methods
     * We only need to call the version using a string as the other one is call by that
     * 
     */
    public void testGetPermissionSet() {
        ZebraSecurity security = (ZebraSecurity) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraSecurity", ZebraSecurity.class);

        PermissionSet results = security.getPermissionSet("bob;jack;harry");
        assertEquals(results.size(), 3);

        Permission[] permissions = results.getPermissionsArray();
        for (Permission permission : permissions) {
            assertNotNull(permission);
            assertNotNull(permission.getName());
        }
    }

    public void createUsers() throws Exception {

        modelManager = (DynamicModelManager) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.hivemind.modelManagerDynamic", ModelManager.class);

        //create permission for creating a user
        permissionManager = (PermissionManager) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.hivemind.permissionManagerDynamic", PermissionManager.class);

        permissionManager.addPermission(permissionManager.getPermissionInstance("ZEBRA_CREATE_USER"));
        permissionManager.addPermission(permissionManager.getPermissionInstance("systemAccess"));
        Permission createUser = permissionManager.getPermissionByName("ZEBRA_CREATE_USER");
        Permission systemAccess = permissionManager.getPermissionByName("systemAccess");

        //create role
        DynamicRole adminRole = null;
        roleManager = (RoleManager) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.hivemind.roleManagerDynamic", RoleManager.class);

        adminRole = (DynamicRole) roleManager.getRoleInstance("ZEBRA_ROLE_ADMINISTRATOR");

        roleManager.addRole(adminRole);

        modelManager.grant(adminRole, createUser);
        modelManager.grant(adminRole, systemAccess);

        DynamicRole normalRole = null;

        normalRole = (DynamicRole) roleManager.getRoleInstance("ZEBRA_ROLE_USER");
        roleManager.addRole(normalRole);
        normalRole.addPermission(systemAccess);
        modelManager.grant(normalRole, systemAccess);

        //create group

        DynamicGroup adminGroup = null;
        DynamicGroup userGroup = null;

        groupManager = (GroupManager) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.hivemind.groupManagerDynamic", GroupManager.class);

        adminGroup = (DynamicGroup) groupManager.getGroupInstance("ZEBRA_GROUP_ADMINISTRATOR");
        userGroup = (DynamicGroup) groupManager.getGroupInstance("ZEBRA_GROUP_USER");
        Role administratorRole = roleManager.getRoleByName("ZEBRA_ROLE_ADMINISTRATOR");
        Role userRole = roleManager.getRoleByName("ZEBRA_ROLE_USER");

        groupManager.addGroup(adminGroup);
        modelManager.grant(adminGroup, administratorRole);

        groupManager.addGroup(userGroup);
        modelManager.grant(userGroup, userRole);

        //create user
        HibernateDynamicUser adminUser;
        HibernateDynamicUser user;

        userManager = (UserManager) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.hivemind.userManagerDynamic", org.apache.fulcrum.security.UserManager.class);

        adminUser = (HibernateDynamicUser) userManager.getUserInstance("ZEBRA_ADMIN_USER");

        user = (HibernateDynamicUser) userManager.getUserInstance("ZEBRA_USER");
        // TODO add authentication stuff
        userManager.addUser(user, "password");
        userManager.addUser(adminUser, "password");
        modelManager.grant(user, userGroup);
        modelManager.grant(adminUser, adminGroup);
    }

    public void testGetTaskList() throws Exception {
        // TODO write me

        createUsers();
        // Start a flow with permissions on it that the user has
        runSimpleWorkflow(YES);

        // Check if the task is on the list

        // start a flow without this permission and then check it is not on the list
    }

    public void runSimpleWorkflow(String test) throws Exception {

        ZebraProcessInstance processInstance = zebra.createProcessPaused(TEST_PERMISSION);
        // assertNotNull(processInstance);

        zebra.startProcess(processInstance);

        List<ZebraTaskInstance> taskList = zebra.getTaskList((HibernateDynamicUser) userManager.getUser("ZEBRA_ADMIN_USER"));

        assertTrue(checkIfInTaskList(taskList, "First Screen"));

        taskList = zebra.getTaskList((HibernateDynamicUser) userManager.getUser("ZEBRA_USER"));
        assertFalse(checkIfInTaskList(taskList, "First Screen"));
        
        testTaskDef(FIRST_SCREEN, processInstance);

        taskList = zebra.getTaskList((HibernateDynamicUser) userManager.getUser("ZEBRA_ADMIN_USER"));
        assertTrue(checkIfInTaskList(taskList, "Second Screen"));
        
        taskList = zebra.getTaskList((HibernateDynamicUser) userManager.getUser("ZEBRA_USER"));
        assertTrue(checkIfInTaskList(taskList, "Second Screen"));
        
        testTaskDef(SECOND_SCREEN, processInstance);

    }

    private boolean checkIfInTaskList(List<ZebraTaskInstance> taskList, String taskName) throws DefinitionNotFoundException {
        boolean inTaskList = false;
        for (ZebraTaskInstance instance : taskList) {
            if (((ZebraTaskDefinition) instance.getTaskDefinition()).getName().equals(taskName)) {
                inTaskList = true;
            }
        }
        return inTaskList;
    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testTaskDef(String taskName, ZebraProcessInstance antelopeProcessInstance) throws Exception {

        //get process
        //check correct process
        //advance flow
        assertEquals(antelopeProcessInstance.getTaskInstances().size(), 1);
        Iterator<ZebraTaskInstance> taskInstanceIterator = antelopeProcessInstance.getTaskInstances().iterator();
        ZebraTaskInstance task = taskInstanceIterator.next();
        assertNotNull(task);
        assertEquals(((ZebraTaskDefinition) task.getTaskDefinition()).getName(), taskName);

        zebra.transitionTask(task);

    }

}
