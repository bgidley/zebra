package org.apache.fulcrum.security.model.dynamic;
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

import org.apache.fulcrum.security.ModelManager;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * Describes all the relationships between entities in the "Dynamic" model.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley</a>
 * @version $Id: DynamicModelManager.java,v 1.1 2005/11/14 18:20:46 bgidley Exp $
 */
public interface DynamicModelManager extends ModelManager
{
    /**
	 * Puts a role into a group
	 * 
	 * This method is used when adding a role to a group.
	 * 
	 * @param group the group to use
	 * @param role the role that will join the group
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the group or role is not present.
	 */
    void grant(Group group, Role role) throws DataBackendException, UnknownEntityException;

    /**
	 * Remove a role from a group
	 * 
	 * This method is used when removeing a role to a group.
	 * 
	 * @param group the group to use
	 * @param role the role that will join the group
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the group or role is not present.
	 */
    void revoke(Group group, Role role) throws DataBackendException, UnknownEntityException;

    /**
	 * Puts a permission in a role
	 * 
	 * This method is used when adding a permission to a role
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the account is not present.
	 */
    void grant(Role role, Permission permission)
        throws DataBackendException, UnknownEntityException;
    /**
	 * Removes a permission from a role
	 * 
	 * @param role the Role.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the user or group is not present.
	 */
    void revoke(Role role, Permission permission)
        throws DataBackendException, UnknownEntityException;

    /**
	 * Puts a user in a group.
	 * 
	 * This method is used when adding a user to a group
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the account is not present.
	 */
    void grant(User user, Group group) throws DataBackendException, UnknownEntityException;
    /**
	 * Removes a user from a group
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the user or group is not present.
	 */
    void revoke(User user, Group group) throws DataBackendException, UnknownEntityException;
    /**
	 * Revokes all roles from an User.
	 * 
	 * This method is typically used when deleting an account.
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the account is not present.
	 */
    void revokeAll(User user) throws DataBackendException, UnknownEntityException;
    /**
	 * Revoke from a permission all roles
	 * 
	 * This method is typically used when deleting a Permission
	 * 
	 * @param permission the Permission.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the permission is not present.
	 */
    void revokeAll(Permission permission) throws DataBackendException, UnknownEntityException;
    /**
	 * Revokes all permissions from a Role.
	 * 
	 * This method is typically used when deleting a Role.
	 * 
	 * @param role the Role
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the Role is not present.
	 */
    void revokeAll(Role role) throws DataBackendException, UnknownEntityException;
    /**
	 * Revokes all roles and users from a Group
	 * 
	 * This method is typically used when deleting a Group.
	 * 
	 * @param group the Group
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the Group is not present.
	 */
    void revokeAll(Group group) throws DataBackendException, UnknownEntityException;
    
    /**
     * Allow B to assumes A's roles, groups and permissions
     * @param delegator A
     * @param delegatee B
     */
    void addDelegate(User delegator, User delegatee) throws DataBackendException, UnknownEntityException;
    
    /**
     * Stop A having B's roles, groups and permissions
     * @param delegate A
     * @param delegatee B
     */
    void removeDelegate(User delegator, User delegatee) throws DataBackendException, UnknownEntityException;;
}
