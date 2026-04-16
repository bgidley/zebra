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
import java.util.Iterator;
import java.util.Map;

import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.RoleSet;
/**
 * This is a control class that makes it easy to find out if a
 * particular User has a given Permission.  It also determines if a
 * User has a a particular Role.
 *
 * @todo Need to rethink the two maps..  Why not just a single list of groups?  That would
 * then cascade down to all the other roles and so on..
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: DynamicAccessControlListImpl.java,v 1.2 2006/03/18 16:19:38 biggus_richus Exp $
 */
public class DynamicAccessControlListImpl implements DynamicAccessControlList
{
	private static final long serialVersionUID = -5180551537096244085L;
	/** The sets of roles that the user has in different groups */
    private Map roleSets;
    /** The sets of permissions that the user has in different groups */
    private Map permissionSets;
    /** The distinct list of groups that this user is part of */
    private GroupSet groupSet = new GroupSet();
    /** The distinct list of roles that this user is part of */
    private RoleSet roleSet = new RoleSet();
    /** the distinct list of permissions that this user has */
    private PermissionSet permissionSet = new PermissionSet();
    /**
     * Constructs a new AccessControlList.
     *
     * This class follows 'immutable' pattern - it's objects can't be modified
     * once they are created. This means that the permissions the users have are
     * in effect form the moment they log in to the moment they log out, and
     * changes made to the security settings in that time are not reflected
     * in the state of this object. If you need to reset an user's permissions
     * you need to invalidate his session. <br>
     * The objects that constructs an AccessControlList must supply hashtables
     * of role/permission sets keyed with group objects. <br>
     *
     * @param roleSets a hashtable containing RoleSet objects keyed with Group objects
     * @param permissionSets a hashtable containing PermissionSet objects keyed with Roles objects
     */
    public DynamicAccessControlListImpl(Map roleSets, Map permissionSets)
    {
        this.roleSets = roleSets;
        this.permissionSets = permissionSets;
        for (Iterator i = roleSets.keySet().iterator(); i.hasNext();)
        {
            Group group = (Group) i.next();
            groupSet.add(group);
            RoleSet rs = (RoleSet) roleSets.get(group);
            roleSet.add(rs);
        }
        for (Iterator i = permissionSets.keySet().iterator(); i.hasNext();)
        {
            Role role = (Role) i.next();
            roleSet.add(role);
            PermissionSet ps = (PermissionSet) permissionSets.get(role);
            permissionSet.add(ps);
        }
    }
    /**
     * Retrieves a set of Roles an user is assigned in a Group.
     *
     * @param group the Group
     * @return the set of Roles this user has within the Group.
     */
    public RoleSet getRoles(Group group)
    {
        if (group == null)
        {
            return null;
        }
        return (RoleSet) roleSets.get(group);
    }
    /**
     * Retrieves a set of Roles an user is assigned in the global Group.
     *
     * @return the set of Roles this user has within the global Group.
     */
    public RoleSet getRoles()
    {
        return roleSet;
    }
    /**
     * Retrieves a set of Permissions an user is assigned in a Group.
     *
     * @param group the Group
     * @return the set of Permissions this user has within the Group.
     */
    public PermissionSet getPermissions(Group group)
    {
        PermissionSet permissionSet = new PermissionSet();
        if (roleSets.containsKey(group))
        {
            RoleSet rs = (RoleSet) roleSets.get(group);
            for (Iterator i = rs.iterator(); i.hasNext();)
            {
                Role role = (Role) i.next();
                if (permissionSets.containsKey(role))
                {
                    permissionSet.add((PermissionSet) permissionSets.get(role));
                }
            }
        }
        return permissionSet;
    }
    /**
     * Retrieves a set of Permissions an user is assigned in the global Group.
     *
     * @return the set of Permissions this user has within the global Group.
     */
    public PermissionSet getPermissions() 
    {
        return permissionSet;
    }
    /**
     * Checks if the user is assigned a specific Role in the Group.
     *
     * @param role the Role
     * @param group the Group
     * @return <code>true</code> if the user is assigned the Role in the Group.
     */
    public boolean hasRole(Role role, Group group)
    {
        RoleSet set = getRoles(group);
        if (set == null || role == null)
        {
            return false;
        }
        return set.contains(role);
    }
    /**
     * Checks if the user is assigned a specific Role in any of the given
     * Groups
     *
     * @param role the Role
     * @param groupset a Groupset
     * @return <code>true</code> if the user is assigned the Role in any of
     *         the given Groups.
     */
    public boolean hasRole(Role role, GroupSet groupset)
    {
        if (role == null)
        {
            return false;
        }
        for (Iterator groups = groupset.iterator(); groups.hasNext();)
        {
            Group group = (Group) groups.next();
            RoleSet roles = getRoles(group);
            if (roles != null)
            {
                if (roles.contains(role))
                {
                    return true;
                }
            }
        }
        return false;
    }
    /**
     * Checks if the user is assigned a specific Role in the Group.
     *
     * @param role the Role
     * @param group the Group
     * @return <code>true</code> if the user is assigned the Role in the Group.
     */
    public boolean hasRole(String role, String group)
    {
        boolean roleFound = false;
        try
        {
            for (Iterator i = roleSets.keySet().iterator(); i.hasNext();)
            {
                Group g = (Group) i.next();
                if (g.getName().equalsIgnoreCase(group))
                {
                    RoleSet rs = (RoleSet) roleSets.get(g);
                    roleFound = rs.containsName(role);
                }
            }
        }
        catch (Exception e)
        {
            roleFound = false;
        }
        return roleFound;
    }
    /**
     * Checks if the user is assigned a specifie Role in any of the given
     * Groups
     *
     * @param rolename the name of the Role
     * @param groupset a Groupset
     * @return <code>true</code> if the user is assigned the Role in any of
     *         the given Groups.
     */
    public boolean hasRole(String rolename, GroupSet groupset)
    {
        Role role;
        try
        {
            role = roleSet.getRoleByName(rolename);
        }
        catch (Exception e)
        {
            return false;
        }
        if (role == null)
        {
            return false;
        }
        for (Iterator groups = groupset.iterator(); groups.hasNext();)
        {
            Group group = (Group) groups.next();
            RoleSet roles = getRoles(group);
            if (roles != null)
            {
                if (roles.contains(role))
                {
                    return true;
                }
            }
        }
        return false;
    }
    /**
     * Checks if the user is assigned a specific Role
     *
     * @param role the Role
     * @return <code>true</code> if the user is assigned the Role in the global Group.
     */
    public boolean hasRole(Role role)
    {
        return roleSet.contains(role);
    }
    /**
     * Checks if the user is assigned a specific Role .
     *
     * @param role the Role
     * @return <code>true</code> if the user is assigned the Role .
     */
    public boolean hasRole(String role)
    {
        try
        {
            return roleSet.containsName(role);
        }
        catch (Exception e)
        {
            return false;
        }
    }
    /**
     * Checks if the user is assigned a specific Permission in the Group.
     *
     * @param permission the Permission
     * @param group the Group
     * @return <code>true</code> if the user is assigned the Permission in the Group.
     */
    public boolean hasPermission(Permission permission, Group group)
    {
        PermissionSet set = getPermissions(group);
        if (set == null || permission == null)
        {
            return false;
        }
        return set.contains(permission);
    }
    /**
     * Checks if the user is assigned a specific Permission in any of the given
     * Groups
     *
     * @param permission the Permission
     * @param groupset a Groupset
     * @return <code>true</code> if the user is assigned the Permission in any
     *         of the given Groups.
     */
    public boolean hasPermission(Permission permission, GroupSet groupset)
    {
        if (permission == null)
        {
            return false;
        }
        for (Iterator groups = groupset.iterator(); groups.hasNext();)
        {
            Group group = (Group) groups.next();
            PermissionSet permissions = getPermissions(group);
            if (permissions != null)
            {
                if (permissions.contains(permission))
                {
                    return true;
                }
            }
        }
        return false;
    }
    /**
     * Checks if the user is assigned a specific Permission in the Group.
     *
     * @param permission the Permission
     * @param group the Group
     * @return <code>true</code> if the user is assigned the Permission in the Group.
     */
    public boolean hasPermission(String permission, String group)
    {
        try
        {
            return hasPermission(permissionSet.getPermissionByName(permission), groupSet.getGroupByName(group));
        }
        catch (Exception e)
        {
            return false;
        }
    }
    /**
     * Checks if the user is assigned a specific Permission in the Group.
     *
     * @param permission the Permission
     * @param group the Group
     * @return <code>true</code> if the user is assigned the Permission in the Group.
     */
    public boolean hasPermission(String permission, Group group)
    {
        try
        {
            return hasPermission(permissionSet.getPermissionByName(permission), group);
        }
        catch (Exception e)
        {
            return false;
        }
    }
    /**
     * Checks if the user is assigned a specifie Permission in any of the given
     * Groups
     *
     * @param permissionName the name of the Permission
     * @param groupset a Groupset
     * @return <code>true</code> if the user is assigned the Permission in any
     *         of the given Groups.
     */
    public boolean hasPermission(String permissionName, GroupSet groupset)
    {
        Permission permission;
        try
        {
            permission = permissionSet.getPermissionByName(permissionName);
        }
        catch (Exception e)
        {
            return false;
        }
        if (permission == null)
        {
            return false;
        }
        for (Iterator groups = groupset.iterator(); groups.hasNext();)
        {
            Group group = (Group) groups.next();
            PermissionSet permissions = getPermissions(group);
            if (permissions != null)
            {
                if (permissions.contains(permission))
                {
                    return true;
                }
            }
        }
        return false;
    }
    /**
     * Checks if the user is assigned a specific Permission.
     *
     * @param permission the Permission
     * @return <code>true</code> if the user is assigned the Permission .
     */
    public boolean hasPermission(Permission permission)
    {
        return permissionSet.contains(permission);
    }
    /**
     * Checks if the user is assigned a specific Permission in the global Group.
     *
     * @param permission the Permission
     * @return <code>true</code> if the user is assigned the Permission in the global Group.
     */
    public boolean hasPermission(String permission)
    {
        try
        {
            return permissionSet.containsName(permission);
        }
        catch (Exception e)
        {
            return false;
        }
    }
}
