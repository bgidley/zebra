package org.apache.fulcrum.security.hibernate.dynamic;
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
import org.apache.fulcrum.security.hibernate.PersistenceHelper;
import org.apache.fulcrum.security.model.dynamic.AbstractDynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.hibernate.Session;
import org.hibernate.Transaction;
/**
 * This implementation persists to a database via Hibernate.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: HibernateModelManagerImpl.java,v 1.1 2005/11/25 08:50:15 bgidley Exp $
 */
public class HibernateModelManagerImpl extends AbstractDynamicModelManager implements DynamicModelManager
{

    private PersistenceHelper persistenceHelper;
    /**
	 * Revokes a Role from a Group.
	 * 
	 * @param group the Group.
	 * @param role the Role.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if group or role is not present.
	 */
    public synchronized void revoke(Group group, Role role)
        throws DataBackendException, UnknownEntityException
    {
        boolean groupExists = false;
        boolean roleExists = false;
        try
        {
            groupExists = getGroupManager().checkExists(group);
            roleExists = getRoleManager().checkExists(role);
            if (groupExists && roleExists)
            {
                ((DynamicGroup) group).removeRole(role);
                ((DynamicRole) role).removeGroup(group);
                getPersistenceHelper().updateEntity(group);
                //updateEntity(role);
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("revoke(Group,Role) failed", e);
        }
        finally
        {
        }
        if (!groupExists)
        {
            throw new UnknownEntityException("Unknown group '" + group.getName() + "'");
        }
        if (!roleExists)
        {
            throw new UnknownEntityException("Unknown role '" + role.getName() + "'");
        }
    }
    /**
	 * Grants a Role a Permission
	 * 
	 * @param role the Role.
	 * @param permission the Permission.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if role or permission is not present.
	 */
    public synchronized void grant(Role role, Permission permission)
        throws DataBackendException, UnknownEntityException
    {
        boolean roleExists = false;
        boolean permissionExists = false;
        try
        {
            roleExists = getRoleManager().checkExists(role);
            permissionExists = getPermissionManager().checkExists(permission);
            
            if (roleExists && permissionExists)
            {
                ((DynamicRole) role).addPermission(permission);
                ((DynamicPermission) permission).addRole(role);
                getPersistenceHelper().updateEntity(permission);
                getPersistenceHelper().updateEntity(role);                
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("grant(Role,Permission) failed", e);
        }
        if (!roleExists)
        {
            throw new UnknownEntityException("Unknown role '" + role.getName() + "'");
        }
        if (!permissionExists)
        {
            throw new UnknownEntityException("Unknown permission '" + permission.getName() + "'");
        }
    }
    /**
	 * Revokes a Permission from a Role.
	 * 
	 * @param role the Role.
	 * @param permission the Permission.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if role or permission is not present.
	 */
    public synchronized void revoke(Role role, Permission permission)
        throws DataBackendException, UnknownEntityException
    {
        boolean roleExists = false;
        boolean permissionExists = false;
        try
        {
            roleExists = getRoleManager().checkExists(role);
            permissionExists = getPermissionManager().checkExists(permission);
            if (roleExists && permissionExists)
            {
                ((DynamicRole) role).removePermission(permission);
                ((DynamicPermission) permission).removeRole(role);
                getPersistenceHelper().updateEntity(role);
                getPersistenceHelper().updateEntity(permission);
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("revoke(Role,Permission) failed", e);
        }
        finally
        {
        }
        if (!roleExists)
        {
            throw new UnknownEntityException("Unknown role '" + role.getName() + "'");
        }
        if (!permissionExists)
        {
            throw new UnknownEntityException("Unknown permission '" + permission.getName() + "'");
        }
    }  

    /**
	 * Puts a user in a group.
	 * 
	 * This method is used when adding a user to a group
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the account is not present.
	 */
    public synchronized void grant(User user, Group group) throws DataBackendException, UnknownEntityException
    {
        boolean groupExists = false;
        boolean userExists = false;
        try
        {
            groupExists = getGroupManager().checkExists(group);
            userExists = getUserManager().checkExists(user);
            if (groupExists && userExists)
            {
                ((DynamicUser) user).addGroup(group);
                ((DynamicGroup) group).addUser(user);
                getPersistenceHelper().updateEntity(group);
                getPersistenceHelper().updateEntity(user);   
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("grant(Role,Permission) failed", e);
        }
        finally
        {
        }
        if (!groupExists)
        {
            throw new UnknownEntityException("Unknown group '" + group.getName() + "'");
        }
        if (!userExists)
        {
            throw new UnknownEntityException("Unknown user '" + user.getName() + "'");
        }
    }
    /**
	 * Removes a user in a group.
	 * 
	 * This method is used when removing a user to a group
	 * 
	 * @param user the User.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if the user or group is not present.
	 */
    public synchronized void revoke(User user, Group group) throws DataBackendException, UnknownEntityException
    {
        boolean groupExists = false;
        boolean userExists = false;
        try
        {
            groupExists = getGroupManager().checkExists(group);
            userExists = getUserManager().checkExists(user);
            if (groupExists && userExists)
            {

                Session session = getPersistenceHelper().retrieveSession();
                Transaction transaction = session.beginTransaction();
				((DynamicUser) user).removeGroup(group);
				((DynamicGroup) group).removeUser(user);                
                session.update(user);
                session.update(group);
                transaction.commit();
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("grant(Role,Permission) failed", e);
        }
        finally
        {
        }
        if (!groupExists)
        {
            throw new UnknownEntityException("Unknown group '" + group.getName() + "'");
        }
        if (!userExists)
        {
            throw new UnknownEntityException("Unknown user '" + user.getName() + "'");
        }
    }


    /**
	 * Grants a Group a Role
	 * 
	 * @param group the Group.
	 * @param role the Role.
	 * @throws DataBackendException if there was an error accessing the data backend.
	 * @throws UnknownEntityException if group or role is not present.
	 */
    public synchronized void grant(Group group, Role role)
        throws DataBackendException, UnknownEntityException
    {
        boolean groupExists = false;
        boolean roleExists = false;
        try
        {
            groupExists = getGroupManager().checkExists(group);
            roleExists = getRoleManager().checkExists(role);
            if (groupExists && roleExists)
            {
                ((DynamicGroup) group).addRole(role);
                ((DynamicRole) role).addGroup(group);
                getPersistenceHelper().updateEntity(group);
                getPersistenceHelper().updateEntity(role);   
                return;
            }
        }
        catch (Exception e)
        {
            throw new DataBackendException("grant(Group,Role) failed", e);
        }
        if (!groupExists)
        {
            throw new UnknownEntityException("Unknown group '" + group.getName() + "'");
        }
        if (!roleExists)
        {
            throw new UnknownEntityException("Unknown role '" + role.getName() + "'");
        }
    }
    
	/**
	 * @return Returns the persistenceHelper.
	 */
	public PersistenceHelper getPersistenceHelper() throws DataBackendException
	{		
		return persistenceHelper;
	}    
 
	/* (non-Javadoc)
	 * @see org.apache.fulcrum.security.model.dynamic.DynamicModelManager#addDelegate(org.apache.fulcrum.security.entity.User, org.apache.fulcrum.security.entity.User)
	 */
	public void addDelegate(User delegator, User delegatee)
			throws DataBackendException, UnknownEntityException {
	
		super.addDelegate(delegator, delegatee);
		getPersistenceHelper().updateEntity(delegator);
		getPersistenceHelper().updateEntity(delegatee);
	}
	
	/* (non-Javadoc)
	 * @see org.apache.fulcrum.security.model.dynamic.DynamicModelManager#removeDelegate(org.apache.fulcrum.security.entity.User, org.apache.fulcrum.security.entity.User)
	 */
	public void removeDelegate(User delegator, User delegatee)
			throws DataBackendException, UnknownEntityException {
	
		super.removeDelegate(delegator, delegatee);
		
		getPersistenceHelper().updateEntity(delegator);
		getPersistenceHelper().updateEntity(delegatee);
	}
    public void setPersistenceHelper(PersistenceHelper persistenceHelper) {
        this.persistenceHelper = persistenceHelper;
    }
}