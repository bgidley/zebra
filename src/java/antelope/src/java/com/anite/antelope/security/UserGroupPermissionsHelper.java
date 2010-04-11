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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
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
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.services.InitializationException;

import com.anite.antelope.utils.AvalonServiceHelper;

/**
 * This class has standard code in it that helps the workflow engine work
 * with the Fulcrum security API.
 * 
 * Specifically whenever a user is created a group and role and permission 
 * with the same name is created and granted. If it does exist it is simply granted. 
 * 
 * @author Ben.Gidley
 */
public class UserGroupPermissionsHelper {

    private final static Log log = LogFactory.getLog(UserGroupPermissionsHelper.class);

    private static UserGroupPermissionsHelper instance;

    private UserManager userManager;

    private DynamicModelManager modelManager;

    private GroupManager groupManager;

    private PermissionManager permissionManager;

    private RoleManager roleManager;

    private SecurityService securityService;

    private UserGroupPermissionsHelper() {
        try {
            SecurityService securityService = AvalonServiceHelper.instance().getSecurityService();
            this.securityService = securityService;
            this.userManager = securityService.getUserManager();
            this.groupManager = securityService.getGroupManager();
            this.modelManager = (DynamicModelManager) securityService.getModelManager();
            this.roleManager = securityService.getRoleManager();
            this.permissionManager = securityService.getPermissionManager();

        } catch (InitializationException e) {
            log.error("Could not get security service", e);
            throw new RuntimeException(e);
        }

    }

    public static UserGroupPermissionsHelper getInstance() {
        if (instance == null) {
            instance = new UserGroupPermissionsHelper();
        }
        return instance;
    }

    /**
     * Create a fulcrum user and a group/role/permission for it 
     * @param userName
     * @param password
     * @return
     * @throws EntityExistsException
     * @throws DataBackendException
     * @throws UnknownEntityException
     */
    public User createUser(String userName, String password) throws EntityExistsException, DataBackendException,
            UnknownEntityException {
        if (userManager.checkExists(userName)) {
            throw new EntityExistsException(userName);
        }

        User user = userManager.getUserInstance(userName);
        userManager.addUser(user, password);

        Group group = createOrFetchGroup(userName);

        modelManager.grant(user, group);
        return user;

    }

    /**
     * Create or fetch a group (and role/permission) for that group) 
     * @param groupName
     * @return
     * @throws DataBackendException
     * @throws UnknownEntityException
     * @throws EntityExistsException
     */
    public Group createOrFetchGroup(String groupName) throws DataBackendException,
            UnknownEntityException, EntityExistsException {

        if (groupManager.checkExists(groupName)) {
            return groupManager.getGroupByName(groupName);
        } else {
            Group group = groupManager.getGroupInstance(groupName);
            groupManager.addGroup(group);
            

            Permission permission;
            if (permissionManager.checkExists(groupName)) {
                permission = permissionManager.getPermissionByName(groupName);
            } else {
                permission = permissionManager.getPermissionInstance(groupName);
                permissionManager.addPermission(permission);
            }

            Role role;
            if (roleManager.checkExists(groupName)) {
                role = roleManager.getRoleByName(groupName);
            } else {
                role = roleManager.getRoleInstance(groupName);
                roleManager.addRole(role);
            }

            modelManager.grant(role, permission);
            modelManager.grant(group, role);
            return group;
        }
    }
        
    public DynamicGroup getUserGroup(DynamicUser user) {
        return (DynamicGroup)user.getGroups().getGroupsArray()[0];
    }

    public void grantUserGroup(DynamicUser user, DynamicGroup newGroup) throws Exception {        
        modelManager.grant(user, newGroup);
    }
    
    /**
     * this method add a permission sepecifically for that user
     * @param user
     * @throws Exception
     */
    public void grantUserSpecificPermission(DynamicUser user, DynamicPermission permission) 
    			throws DataBackendException, UnknownEntityException
    {
        DynamicModelManager modelManager = getModelManager();
        modelManager.grant(getUserSpecificRole(user), permission);        
    }
    
    /**
     * Revoke a permission that has been allocated to the user secific group/role
     * @param user
     * @param permission
     * @throws Exception
     */
    public void revokeUserSpecificPermission(DynamicUser user, DynamicPermission permission) throws Exception {
        DynamicModelManager modelManager = getModelManager();
        modelManager.revoke(getUserSpecificRole(user), permission);        
    }
    
    /**
     * Get the role that has been created esp for the user to add 
     * user specific permissions
     * @param user
     * @return
     */
    protected DynamicRole getUserSpecificRole(DynamicUser user)  {
        // this gets the specific users group
        GroupSet usergroups = user.getGroups();
        DynamicGroup group = (DynamicGroup) usergroups.getByName(user.getName());
        return (DynamicRole) group.getRoles().getRoleByName(user.getName());
    }


    /**
     * @return Returns the groupManager.
     */
    public GroupManager getGroupManager() {
        return groupManager;
    }

    /**
     * @return Returns the modelManager.
     */
    public DynamicModelManager getModelManager() {
        return modelManager;
    }

    /**
     * @return Returns the permissionManager.
     */
    public PermissionManager getPermissionManager() {
        return permissionManager;
    }

    /**
     * @return Returns the roleManager.
     */
    public RoleManager getRoleManager() {
        return roleManager;
    }

    /**
     * @return Returns the userManager.
     */
    public UserManager getUserManager() {
        return userManager;
    }

    /**
     * @return Returns the securityService.
     */
    public SecurityService getSecurityService() {
        return securityService;
    }
}