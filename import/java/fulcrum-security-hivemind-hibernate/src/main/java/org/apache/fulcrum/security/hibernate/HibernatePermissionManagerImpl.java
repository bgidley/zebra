package org.apache.fulcrum.security.hibernate;

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
import java.util.List;

import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.spi.AbstractPermissionManager;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.hibernate.HibernateException;
import org.hibernate.Query;

/**
 * This implementation persists to a database via Hibernate.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: HibernatePermissionManagerImpl.java,v 1.2 2006/03/18 16:18:21 biggus_richus Exp $
 */
public class HibernatePermissionManagerImpl extends AbstractPermissionManager {
    private PersistenceHelper persistenceHelper;

    /**
     * Retrieves all permissions defined in the system.
     *
     * @return the names of all roles defined in the system.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     */
    public PermissionSet getAllPermissions() throws DataBackendException {
        PermissionSet permissionSet = new PermissionSet();
        try {
            Query permissionQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + "");
            List permissions = permissionQuery.list();
            permissionSet.add(permissions);

        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving permission information", e);
        }
        return permissionSet;
    }

    /**
     * Retrieves all non-disabled permissions defined in the system.
     *
     * @return the names of all non-disabled roles defined in the system.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     */
    public PermissionSet getPermissions() throws DataBackendException {
        PermissionSet permissionSet = new PermissionSet();
        try {
            Query permissionQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + " p where p.disabled = false");
            List permissions = permissionQuery.list();
            permissionSet.add(permissions);

        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving permission information", e);
        }
        return permissionSet;
    }

    /**
     * Renames an existing Permission.
     *
     * @param permission The object describing the permission to be renamed.
     * @param name the new name for the permission.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the permission does not exist.
     */
    public synchronized void renamePermission(Permission permission, String name) throws DataBackendException,
            UnknownEntityException {
        boolean permissionExists = false;
        permissionExists = checkExists(permission);
        if (permissionExists) {
            permission.setName(name);
            getPersistenceHelper().updateEntity(permission);
            return;
        } else {
            throw new UnknownEntityException("Unknown permission '" + permission + "'");
        }
    }

    /**
     * Determines if the <code>Permission</code> exists in the security system.
     *
     * @param permissionName a <code>Permission</code> value
     * @return true if the permission name exists in the system, false otherwise
     * @throws DataBackendException when more than one Permission with
     *         the same name exists.
     */
    public boolean checkExists(String permissionName) throws DataBackendException {
        List permissions;
        try {
            Query permissionQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + " sp where sp.name=:name");
            permissionQuery.setString("name", permissionName);
            permissions = permissionQuery.list();

        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving permission information", e);
        }
        if (permissions.size() > 1) {
            throw new DataBackendException("Multiple permissions with same name '" + permissionName + "'");
        }
        return (permissions.size() == 1);
    }

    /**
     * Disables a Permission (effectively rendering it as removed).
     *
     * @param permission The object describing the permission to be removed.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the permission does not exist.
     */
    public synchronized void disablePermission(Permission permission) throws DataBackendException, UnknownEntityException {
        getPersistenceHelper().disableEntity(permission);
    }

    /**
     * Removes a Permission from the system.
     *
     * @param permission The object describing the permission to be removed.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the permission does not exist.
     */
    public synchronized void removePermission(Permission permission) throws DataBackendException, UnknownEntityException {
        getPersistenceHelper().removeEntity(permission);
    }

    /**
     * Creates a new permission with specified attributes.
     *
     * @param permission the object describing the permission to be created.
     * @return a new Permission object that has id set up properly.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws EntityExistsException if the permission already exists.
     */
    protected synchronized Permission persistNewPermission(Permission permission) throws DataBackendException {

        getPersistenceHelper().addEntity(permission);
        return permission;
    }

    /**
     * @return Returns the persistenceHelper.
     */
    public PersistenceHelper getPersistenceHelper() throws DataBackendException {

        return persistenceHelper;
    }

    /**
     * Retrieve a Permission object with specified id.
     * 
     * @param id
     *            the id of the Permission.
     * @return an object representing the Permission with specified id.
     * @throws DataBackendException
     *             if there was an error accessing the data backend.
     * @throws UnknownEntityException
     *             if the permission does not exist.
     */
    public Permission getPermissionById(Object id) throws DataBackendException, UnknownEntityException {

        Permission permission = null;

        if (id != null)
            try {
                Query permissionQuery = getPersistenceHelper().retrieveSession().createQuery(
                        "from " + getClassName() + " sp where sp.id=:id");

                permissionQuery.setLong("id", (Long) id);

                List permissions = permissionQuery.list();
                if (permissions.size() == 0) {
                    throw new UnknownEntityException("Could not find permission by id " + id);
                }
                permission = (Permission) permissions.get(0);

            } catch (HibernateException e) {
                throw new DataBackendException("Error retriving permission information", e);
            }

        return permission;
    }

    public void setPersistenceHelper(PersistenceHelper persistenceHelper) {
        this.persistenceHelper = persistenceHelper;
    }
}
