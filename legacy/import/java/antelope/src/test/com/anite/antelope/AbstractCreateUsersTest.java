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

import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.testcontainer.BaseUnitTest;
import org.apache.turbine.util.TurbineConfig;

import com.anite.antelope.security.UserGroupPermissionsHelper;
import com.anite.antelope.utils.AntelopeConstants;

/**
 * This in a absract class the will build up a set of users/groups/roles and
 * premission for Antelope.
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public abstract class AbstractCreateUsersTest extends BaseUnitTest {

    private static final String BASIC = "basic";
    private static final String ANTELOPE = "antelope";
    private static final String SYSTEMACCESS = "systemAccess";

    /**
     * @param arg0
     */
    public AbstractCreateUsersTest(String arg0) {
        super(arg0);
        //   Initialise Fake Turbine so it can resolve Avalon
        // In theory calling this twice should only initialise once
		TurbineConfig config = null;
		config = new TurbineConfig("./src/webapp/", "WEB-INF/conf/TurbineResources.properties");
		config.initialize();
        

    }

    protected SecurityService securityService;

    protected DynamicModelManager modelManager;

    protected UserManager userManager;

    protected GroupManager groupManager;

    protected RoleManager roleManager;

    protected PermissionManager permissionManager;

    public void testCreateUsers() throws Exception {
        User user;
        Group group;
        Role role;
        Permission permission;

        // build up a simple dynanic user permission model
        modelManager = (DynamicModelManager) securityService.getModelManager();

        // get all the managers
        userManager = securityService.getUserManager();
        groupManager = securityService.getGroupManager();
        roleManager = securityService.getRoleManager();
        permissionManager = securityService.getPermissionManager();

        // Add all the permissions
        permission = permissionManager
                .getPermissionInstance(AntelopeConstants.PERMISSION_ADD_USER);
        permissionManager.addPermission(permission);
        permission = permissionManager
                .getPermissionInstance(AntelopeConstants.PERMISSION_EDIT_PERMISSIONS);
        permissionManager.addPermission(permission);
        permission = permissionManager
                .getPermissionInstance(AntelopeConstants.PERMISSION_CHANGE_PASSWORD);
        permissionManager.addPermission(permission);
        permission = permissionManager.getPermissionInstance("security_add");
        permissionManager.addPermission(permission);
        permission = permissionManager.getPermissionInstance("security_edit");
        permissionManager.addPermission(permission);
        permission = permissionManager.getPermissionInstance("security_delete");
        permissionManager.addPermission(permission);
        permission = permissionManager
                .getPermissionInstance(AntelopeConstants.PERMISSION_SYSTEM_ACCESS);
        permissionManager.addPermission(permission);

        // Add all roles
        role = roleManager.getRoleInstance(AntelopeConstants.ROLE_USER_ADMIN);
        roleManager.addRole(role);
        role = roleManager.getRoleInstance("security");
        roleManager.addRole(role);
        role = roleManager.getRoleInstance(AntelopeConstants.ROLE_USER_BASIC);
        roleManager.addRole(role);
        role = roleManager.getRoleInstance(SYSTEMACCESS);
        roleManager.addRole(role);

        // Add all Groups
        UserGroupPermissionsHelper.getInstance().createOrFetchGroup(
                AntelopeConstants.GROUP_ADMIN);
        UserGroupPermissionsHelper.getInstance().createOrFetchGroup(
                AntelopeConstants.GROUP_BASIC);
        UserGroupPermissionsHelper.getInstance().createOrFetchGroup("test2");
        UserGroupPermissionsHelper.getInstance().createOrFetchGroup("test3");

        // add all users
        UserGroupPermissionsHelper.getInstance().createUser(ANTELOPE, "test");
        UserGroupPermissionsHelper.getInstance().createUser(BASIC, "test");

        // set up the stutcuture
        // add perms to roles
        modelManager
                .grant(
                        roleManager
                                .getRoleByName(AntelopeConstants.ROLE_USER_ADMIN),
                        permissionManager
                                .getPermissionByName(AntelopeConstants.PERMISSION_ADD_USER));
        modelManager
                .grant(
                        roleManager
                                .getRoleByName(AntelopeConstants.ROLE_USER_ADMIN),
                        permissionManager
                                .getPermissionByName(AntelopeConstants.PERMISSION_EDIT_PERMISSIONS));
        modelManager
                .grant(
                        roleManager
                                .getRoleByName(AntelopeConstants.ROLE_USER_ADMIN),
                        permissionManager
                                .getPermissionByName(AntelopeConstants.PERMISSION_CHANGE_PASSWORD));

        modelManager
                .grant(
                        roleManager
                                .getRoleByName(AntelopeConstants.ROLE_USER_BASIC),
                        permissionManager
                                .getPermissionByName(AntelopeConstants.PERMISSION_CHANGE_PASSWORD));

        modelManager.grant(roleManager.getRoleByName("security"),
                permissionManager.getPermissionByName("security_add"));
        modelManager.grant(roleManager.getRoleByName("security"),
                permissionManager.getPermissionByName("security_edit"));
        modelManager.grant(roleManager.getRoleByName("security"),
                permissionManager.getPermissionByName("security_delete"));
        modelManager
                .grant(
                        roleManager.getRoleByName(SYSTEMACCESS),
                        permissionManager
                                .getPermissionByName(AntelopeConstants.PERMISSION_SYSTEM_ACCESS));

        // add roles to groups
        modelManager.grant(groupManager
                .getGroupByName(AntelopeConstants.GROUP_ADMIN), roleManager
                .getRoleByName(AntelopeConstants.ROLE_USER_ADMIN));
        modelManager.grant(groupManager
                .getGroupByName(AntelopeConstants.GROUP_ADMIN), roleManager
                .getRoleByName("security"));
        modelManager.grant(groupManager
                .getGroupByName(AntelopeConstants.GROUP_BASIC), roleManager
                .getRoleByName(AntelopeConstants.ROLE_USER_BASIC));
        modelManager.grant(groupManager
                .getGroupByName(AntelopeConstants.GROUP_BASIC), roleManager
                .getRoleByName(SYSTEMACCESS));
        modelManager.grant(groupManager
                .getGroupByName(AntelopeConstants.GROUP_ADMIN), roleManager
                .getRoleByName(SYSTEMACCESS));

        // add groups to users
        modelManager.grant(userManager.getUser(ANTELOPE), groupManager
                .getGroupByName(AntelopeConstants.GROUP_ADMIN));
        modelManager.grant(userManager.getUser(BASIC), groupManager
                .getGroupByName(AntelopeConstants.GROUP_BASIC));

    }
}