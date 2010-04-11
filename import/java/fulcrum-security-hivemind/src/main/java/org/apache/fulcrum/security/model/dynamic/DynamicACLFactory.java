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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;

import org.apache.fulcrum.security.acl.AccessControlList;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.ACLFactory;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.spi.AbstractManager;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * 
 * This factory creates instance of the DynamicAccessControlList
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh </a>
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley </a>
 * @version $Id: DynamicACLFactory.java,v 1.2 2006/03/18 16:19:38 biggus_richus Exp $
 */
public class DynamicACLFactory extends AbstractManager implements ACLFactory {
	/**
	 * Construct a new ACL object.
	 * 
	 * This constructs a new ACL object from the configured class and
	 * initializes it with the supplied roles and permissions.
	 * 
	 * @param roles
	 *            The roles that this ACL should contain
	 * @param permissions
	 *            The permissions for this ACL
	 * 
	 * @return an object implementing ACL interface.
	 * @throws UnknownEntityException
	 *             if the object could not be instantiated.
	 */
	private AccessControlList getAclInstance(Map roles, Map permissions)
			throws UnknownEntityException {
		AccessControlList accessControlList;
		try {
			/*
			 * 
			 * @todo I think this is overkill for now.. accessControlList =
			 * (AccessControlList)
			 * aclFactoryService.getInstance(aclClass.getName(), objects,
			 * signatures);
			 */
			accessControlList = new DynamicAccessControlListImpl(roles,
					permissions);
		} catch (Exception e) {
			throw new UnknownEntityException(
					"Failed to instantiate an ACL implementation object", e);
		}
		return accessControlList;
	}

	@SuppressWarnings("unchecked")
	public AccessControlList getAccessControlList(User user) {
		Map roleSets = new HashMap();
		Map permissionSets = new HashMap();

		Set users = new HashSet();
		// add the root user
		users.add(user);
		addDelegators((DynamicUser) user, users);

		Iterator i = users.iterator();
		while (i.hasNext()) {
			DynamicUser aUser = (DynamicUser) i.next();
			addRolesAndPermissions(aUser, roleSets, permissionSets);
		}

		try {
			return getAclInstance(roleSets, permissionSets);
		} catch (UnknownEntityException uue) {
			throw new RuntimeException(uue.getMessage(), uue);
		}
	}

	@SuppressWarnings("unchecked")
	public void addDelegators(DynamicUser user, Set users) {
		for (Iterator iter = user.getDelegators().iterator(); iter.hasNext();) {
			DynamicUser delegatorUser = (DynamicUser) iter.next();

			if (users.add(delegatorUser)) {
				// Only come here if user NOT in users
				addDelegators(delegatorUser, users);
			}
		}
	}

	/**
	 * Adds the passed users roles and permissions to the sets As maps overwrite
	 * duplicates we just put it in an let it overwrite it is probably quicker
	 * than checking for duplicates
	 * 
	 * @param user
	 * @param roleSets
	 * @param permissionSets
	 */
	@SuppressWarnings("unchecked")
	private void addRolesAndPermissions(User user, Map roleSets,
			Map permissionSets) {
		for (Iterator i = ((DynamicUser) user).getGroups().iterator(); i
				.hasNext();) {
			Group group = (Group) i.next();
			RoleSet roleSet = (RoleSet) ((DynamicGroup) group).getRoles();
			roleSets.put(group, roleSet);
			for (Iterator j = roleSet.iterator(); j.hasNext();) {
				DynamicRole role = (DynamicRole) j.next();
				permissionSets.put(role, role.getPermissions());
			}
		}
	}

}