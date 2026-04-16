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
 * The Security Service manages Users, Groups Roles and Permissions in the system.
 * 
 * The task performed by the security service include providing access to the various types of
 * managers.
 * 
 * <p>
 * Because of pluggable nature of the Services, it is possible to create multiple implementations
 * of SecurityService, for example employing database and directory server as the data backend.
 * <br>
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: SecurityService.java,v 1.1 2005/11/14 18:20:47 bgidley Exp $
 */
public interface SecurityService {
    /**
     * Returns the configured UserManager.
     * 
     * @return An UserManager object
     */
    UserManager getUserManager();
    /**
     * Returns the configured GroupManager.
     * 
     * @return An UserManager object
     */
    GroupManager getGroupManager();
    /**
     * Returns the configured RoleManager.
     * 
     * @return An RoleManager object
     */
    RoleManager getRoleManager();
    /**
     * Returns the configured PermissionManager.
     * 
     * @return An PermissionManager object
     */
    PermissionManager getPermissionManager();
    /**
     * Returns the configured ModelManager object that can then
     * be casted to the specific model.
     * 
     * @return An ModelManager object
     */
    ModelManager getModelManager();    

}
