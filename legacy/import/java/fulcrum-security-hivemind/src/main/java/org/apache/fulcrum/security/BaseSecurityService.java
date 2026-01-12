package org.apache.fulcrum.security;
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

/**
 * This a basis implementation of the Fulcrum security service.
 * 
 * Provided functionality includes:
 * <ul>
 * <li>methods for retrieving different types of managers.
 * <li>avalon lifecyle managers.
 * </ul>
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric PUgh</a>
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley</a>
 * @version $Id: BaseSecurityService.java,v 1.1 2005/11/14 18:20:47 bgidley Exp $
 */

public class BaseSecurityService implements SecurityService {

    protected ModelManager modelManager;
    protected GroupManager groupManager;
    protected PermissionManager permissionManager;
    protected RoleManager roleManager;
    protected UserManager userManager;
    
    public GroupManager getGroupManager() {
        return groupManager;
    }
    public void setGroupManager(GroupManager groupManager) {
        this.groupManager = groupManager;
    }
    public ModelManager getModelManager() {
        return modelManager;
    }
    public void setModelManager(ModelManager modelManager) {
        this.modelManager = modelManager;
    }
    public PermissionManager getPermissionManager() {
        return permissionManager;
    }
    public void setPermissionManager(PermissionManager permissionManager) {
        this.permissionManager = permissionManager;
    }
    public RoleManager getRoleManager() {
        return roleManager;
    }
    public void setRoleManager(RoleManager roleManager) {
        this.roleManager = roleManager;
    }
    public UserManager getUserManager() {
        return userManager;
    }
    public void setUserManager(UserManager userManager) {
        this.userManager = userManager;
    }
    
}
