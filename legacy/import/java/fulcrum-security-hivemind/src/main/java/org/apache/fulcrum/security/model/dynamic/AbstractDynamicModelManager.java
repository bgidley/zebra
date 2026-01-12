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

import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.spi.AbstractManager;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * Holds shared functionality between different implementations of
 * DyanamicModelManager's.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh </a>
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley</a>
 * @version $Id: AbstractDynamicModelManager.java,v 1.2 2004/07/07 18:18:09
 *          epugh Exp $
 */
public abstract class AbstractDynamicModelManager extends AbstractManager
		implements DynamicModelManager {
	/**
	 * Revokes all roles from a permission
	 * 
	 * This method is used when deleting a permission.
	 * 
	 * @param permission
	 *            the permission.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the account is not present.
	 */
	public synchronized void revokeAll(Permission permission)
			throws DataBackendException, UnknownEntityException {
		boolean permissionExists = false;
		permissionExists = getPermissionManager().checkExists(permission);
		if (permissionExists) {
			Object roles[] = ((DynamicPermission) permission).getRoles()
					.toArray();
			for (int i = 0; i < roles.length; i++) {
				revoke((Role) roles[i], permission);
			}

			return;
		} else {
			throw new UnknownEntityException("Unknown permission '"
					+ permission.getName() + "'");
		}
	}

	/**
	 * Revokes all users and roles from a group
	 * 
	 * This method is used when deleting a group.
	 * 
	 * @param group
	 *            the Group.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the account is not present.
	 */
	public synchronized void revokeAll(Group group)
			throws DataBackendException, UnknownEntityException {
		boolean groupExists = false;
		groupExists = getGroupManager().checkExists(group);
		if (groupExists) {
			Object users[] = ((DynamicGroup) group).getUsers().toArray();
			for (int i = 0; i < users.length; i++) {
				revoke((User) users[i], group);
			}

			Object roles[] = ((DynamicGroup) group).getRoles().toArray();
			for (int i = 0; i < roles.length; i++) {
				revoke(group, (Role) roles[i]);
			}

			return;
		} else {
			throw new UnknownEntityException("Unknown group '"
					+ group.getName() + "'");
		}
	}

	/**
	 * Revokes all groups from a user
	 * 
	 * This method is used when deleting an account.
	 * 
	 * @param user
	 *            the User.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the account is not present.
	 */
	public synchronized void revokeAll(User user) throws DataBackendException,
			UnknownEntityException {
		boolean userExists = false;
		userExists = getUserManager().checkExists(user);
		if (userExists) {
			Object groups[] = ((DynamicUser) user).getGroups().toArray();
			for (int i = 0; i < groups.length; i++) {
				revoke(user, (Group) groups[i]);
			}

			return;
		} else {
			throw new UnknownEntityException("Unknown user '" + user.getName()
					+ "'");
		}
	}

	/**
	 * Revokes all permissions and groups from a Role.
	 * 
	 * This method is used when deleting a Role.
	 * 
	 * @param role
	 *            the Role
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the Role is not present.
	 */
	public synchronized void revokeAll(Role role) throws DataBackendException,
			UnknownEntityException {
		boolean roleExists = false;
		roleExists = getRoleManager().checkExists(role);
		if (roleExists) {
			Object groups[] = ((DynamicRole) role).getGroups().toArray();
			for (int i = 0; i < groups.length; i++) {
				revoke((Group) groups[i], role);
			}

			Object permissions[] = ((DynamicRole) role).getPermissions()
					.toArray();
			for (int i = 0; i < permissions.length; i++) {
				revoke(role, (Permission) permissions[i]);
			}
		} else {
			throw new UnknownEntityException("Unknown role '" + role.getName()
					+ "'");
		}

	}

	/**
	 * It is expected the real implementation will overide this and save either
	 * side of the function. It is not abstract as a in memory implementation
	 * would not need to do anything.
	 */
	@SuppressWarnings("unchecked")
	public void addDelegate(User delegator, User delegatee)
			throws DataBackendException, UnknownEntityException {
		DynamicUser dynamicDelegator = (DynamicUser) delegator;
		DynamicUser dynamicDelegatee = (DynamicUser) delegatee;

		// check it hasn't already been done
		// It is NOT an error to call this twice
		if (!(dynamicDelegator.getDelegatees().contains(delegatee) || dynamicDelegatee
				.getDelegators().contains(delegator))) {
			dynamicDelegator.getDelegatees().add(dynamicDelegatee);
			dynamicDelegatee.getDelegators().add(dynamicDelegator);
		}
	}

	/**
	 * Implementors should overide this to save and call super if
	 * they want the base class to do the work
	 */
	public void removeDelegate(User delegator, User delegatee)
			throws DataBackendException, UnknownEntityException {
		DynamicUser dynamicDelegator = (DynamicUser) delegator;
		DynamicUser dynamicDelegatee = (DynamicUser) delegatee;

		if (dynamicDelegator.getDelegatees().contains(dynamicDelegatee)){
			dynamicDelegator.getDelegatees().remove(dynamicDelegatee);
			dynamicDelegatee.getDelegators().remove(dynamicDelegator);
		}else {
			throw new UnknownEntityException("Tried to remove a delegate that does not exist");
		}

	}
}