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
import org.apache.fulcrum.security.entity.impl.SecurityEntityImpl;
import org.apache.fulcrum.security.util.RoleSet;

/**
 * Represents the "simple" model where permissions are related to roles,
 * roles are related to groups and groups are related to users,
 * all in many to many relationships.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: DynamicPermission.java,v 1.3 2006/07/19 09:15:17 bgidley Exp $
 */
public class DynamicPermission extends SecurityEntityImpl implements Permission
{
    private Set roleSet = new RoleSet();

    /**
     * @return
     */
    public RoleSet getRoles() {
    	
    	return new RoleSet(roleSet);
    }

    /**
     * @param roleSet
     */
    public void setRoles(RoleSet roleSet) {
        if (roleSet != null)
            this.roleSet = roleSet;
        else
            this.roleSet = new RoleSet();
    }

    /**
     * Add a role to the RoleSet
     * @param role the role to add
     */
    public void addRole(Role role) {
        getRoles().add(role);
    }

    /**
     * Remove a role from the RoleSet
     * @param role the role to remove
     */
    public void removeRole(Role role) {
        getRoles().remove(role);
    }

    /**
     * 
     * @param roles
     */
    public void setRolesAsSet(Set roles) {
        this.roleSet = roles;
    }

    /**
     * 
     * @return
     */
    public Set getRolesAsSet() {
        return roleSet;
    }
}