package org.apache.fulcrum.security.util;

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

import java.util.Collection;
import java.util.Iterator;
import java.util.Set;

import org.apache.fulcrum.security.entity.Role;

/**
 * This class represents a set of Roles.  It makes it easy to build a
 * UI that would allow someone to add a group of Roles to a User.
 * It enforces that only Role objects are
 * allowed in the set and only relevant methods are available.
 *
 * @author <a href="mailto:john.mcnally@clearink.com">John D. McNally</a>
 * @author <a href="mailto:bmclaugh@algx.net">Brett McLaughlin</a>
 * @author <a href="mailto:marco@intermeta.de">Marco Kn&uuml;ttel</a>
 * @author <a href="mailto:hps@intermeta.de">Henning P. Schmiedehausen</a>
 * @version $Id: RoleSet.java,v 1.3 2006/07/19 09:15:16 bgidley Exp $
 */
public class RoleSet
        extends SecuritySet
{
	private static final long serialVersionUID = -7878336668034575930L;

	/**
     * Constructs an empty RoleSet
     */
    public RoleSet()
    {
        super();
    }

    /**
     * Constructs a new RoleSet with specified contents.
     *
     * If the given collection contains multiple objects that are
     * identical WRT equals() method, some objects will be overwritten.
     *
     * @param roles A collection of roles to be contained in the set.
     */
    public RoleSet(Set roles)
    {
        this.wrappedSet = roles;
    }

    /**
     * Adds a Role to this RoleSet.
     *
     * @param role A Role.
     * @return True if Role was added; false if RoleSet already
     * contained the Role.
     */
    @SuppressWarnings("unchecked")
	public boolean add(Role role)
    {
    	return wrappedSet.add(role);
    }
    
    /**
     * Adds a Role to this RoleSet.
     *
     * @param obj A Role.
     * @return True if Role was added; false if RoleSet already
     * contained the Role.
     */
    public boolean add(Object obj) {
        if(obj instanceof Role){
            return add((Role)obj);
        }
        else {
            throw new ClassCastException("Object passed to add to RoleSet is not of type Role");
        }
    }

    /**
     * Adds the Roles in a Collection to this RoleSet.
     *
     * @param roles A Collection of Roles.
     * @return True if this RoleSet changed as a result; false
     * if no change to this RoleSet occurred (this RoleSet
     * already contained all members of the added RoleSet).
     */
    public boolean add(Collection roles)
    {
        boolean res = false;
        for (Iterator it = roles.iterator(); it.hasNext();)
        {
            Role r = (Role) it.next();
            res |= add(r);
        }
        return res;
    }

    /**
     * Adds the Roles in another RoleSet to this RoleSet.
     *
     * @param roleSet A RoleSet.
     * @return True if this RoleSet changed as a result; false
     * if no change to this RoleSet occurred (this RoleSet
     * already contained all members of the added RoleSet).
     */
    public boolean add(RoleSet roleSet)
    {
        boolean res = false;
        for( Iterator it = roleSet.iterator(); it.hasNext();)
        {
            Role r = (Role) it.next();
            res |= add(r);
        }
        return res;
    }

    /**
     * Removes a Role from this RoleSet.
     *
     * @param role A Role.
     * @return True if this RoleSet contained the Role
     * before it was removed.
     */
    public boolean remove(Role role)
    {
    	return wrappedSet.remove(role);
    }

    /**
     * Checks whether this RoleSet contains a Role.
     *
     * @param role A Role.
     * @return True if this RoleSet contains the Role,
     * false otherwise.
     */
    public boolean contains(Role role)
    {
		return super.contains(role);
    }


    /**
     * Returns a Role with the given name, if it is contained in
     * this RoleSet.
     *
     * @param roleName Name of Role.
     * @return Role if argument matched a Role in this
     * RoleSet; null if no match.
     */
    public Role getRoleByName(String roleName)
    {
		return (Role)getByName(roleName);	
    }

    /**
     * Returns a Role with the given id, if it is contained in this
     * RoleSet.
     *
     * @param roleId id of the Role.
     * @return Role if argument matched a Role in this RoleSet; null
     * if no match.
     */
    public Role getRoleById(Object roleId)
    {
        return (roleId != null) 
                ? (Role) super.getById(roleId) : null;
    }

    /**
     * Returns an Array of Roles in this RoleSet.
     *
     * @return An Array of Role objects.
     */
    @SuppressWarnings("unchecked")
	public Role[] getRolesArray()
    {
        return (Role[]) getSet().toArray(new Role[0]);
    }

    /**
     * Print out a RoleSet as a String
     *
     * @returns The Role Set as String
     *
     */
    public String toString()
    {
        StringBuffer sb = new StringBuffer();
        sb.append("RoleSet: ");

        for(Iterator it = iterator(); it.hasNext();)
        {
            Role r = (Role) it.next();
            sb.append('[');
            sb.append(r.getName());
            sb.append(" -> ");
            sb.append(r.getId());
            sb.append(']');
            if (it.hasNext())
            {
                sb.append(", ");
            }
        }

        return sb.toString();
    }


}
