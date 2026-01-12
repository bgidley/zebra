package org.apache.fulcrum.security.model.dynamic.entity;

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

import java.util.Set;

import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.impl.SecurityEntityImpl;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.PermissionSet;

/**
 * Represents the "simple" model where permissions are related to roles, roles
 * are related to groups and groups are related to users, all in many to many
 * relationships.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: DynamicRole.java,v 1.3 2006/07/19 09:15:17 bgidley Exp $
 */
public class DynamicRole extends SecurityEntityImpl implements Role {
	private Set permissionSet = new PermissionSet();

	private Set groupSet = new GroupSet();

	/**
	 * @return
	 */
	public PermissionSet getPermissions() {

		return new PermissionSet(permissionSet);

	}

	/**
	 * @return
	 */
	public Set getPermissionsAsSet() {
		return permissionSet;
	}

	public void setPermissionsAsSet(Set permissions) {
		this.permissionSet = permissions;
		;
	}

	/**
	 * @param permissionSet
	 */
	public void setPermissions(PermissionSet permissionSet) {
		if (permissionSet != null)
			this.permissionSet = permissionSet;
		else
			this.permissionSet = new PermissionSet();
	}

	/**
	 * This method should only be used by a RoleManager. Not directly.
	 * 
	 * @param permission
	 */
	public void addPermission(Permission permission) {
		getPermissions().add(permission);
	}

	/**
	 * This method should only be used by a RoleManager. Not directly.
	 * 
	 * @param permission
	 */
	public void removePermission(Permission permission) {
		getPermissions().remove(permission);
	}

	/**
	 * @return
	 */
	public GroupSet getGroups() {

		return new GroupSet(groupSet);

	}

	/**
	 * @param groupSet
	 */
	public void setGroups(GroupSet groupSet) {
		if (groupSet != null)
			this.groupSet = groupSet;
		else
			this.groupSet = new GroupSet();
	}

	/**
	 * This method should only be used by a RoleManager. Not directly.
	 * 
	 * @param group
	 */
	public void addGroup(Group group) {
		getGroups().add(group);
	}

	/**
	 * This method should only be used by a RoleManager. Not directly.
	 * 
	 * @param group
	 */
	public void removeGroup(Group group) {
		getGroups().remove(group);
	}

	public void setGroupsAsSet(Set groups) {
		this.groupSet = groups;
	}

	public Set getGroupsAsSet() {
		return groupSet;
	}
}