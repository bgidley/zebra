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
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * An GroupManager performs {@link org.apache.fulcrum.security.entity.Group}
 * objects related tasks on behalf of the
 * {@link org.apache.fulcrum.security.BaseSecurityService}.
 * 
 * The responsibilities of this class include loading data of an group from the
 * storage and putting them into the
 * {@link org.apache.fulcrum.security.entity.Group} objects, saving those data
 * to the permanent storage.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: PermissionManager.java,v 1.2 2006/03/18 16:19:38 biggus_richus Exp $
 */
public interface PermissionManager {

	/**
	 * Construct a blank Permission object.
	 * 
	 * This method calls getPermissionClass, and then creates a new object using
	 * the default constructor.
	 * 
	 * @return an object implementing Permission interface.
	 * @throws UnknownEntityException
	 *             if the object could not be instantiated.
	 */
	Permission getPermissionInstance() throws UnknownEntityException;

	/**
	 * Construct a blank Permission object.
	 * 
	 * This method calls getPermissionClass, and then creates a new object using
	 * the default constructor.
	 * 
	 * @param permName
	 *            The name of the Permission
	 * 
	 * @return an object implementing Permission interface.
	 * @throws UnknownEntityException
	 *             if the object could not be instantiated.
	 */
	Permission getPermissionInstance(String permName)
			throws UnknownEntityException;

	/**
	 * Retrieve a Permission object with specified name.
	 * 
	 * @param name
	 *            the name of the Permission.
	 * @return an object representing the Permission with specified name.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the permission does not exist.
	 */
	Permission getPermissionByName(String name) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Retrieve a Permission object with specified Id.
	 * 
	 * @param name
	 *            the name of the Permission.
	 * 
	 * @return an object representing the Permission with specified name.
	 * 
	 * @exception UnknownEntityException
	 *                if the permission does not exist in the database.
	 * @exception DataBackendException
	 *                if there is a problem accessing the storage.
	 */
	Permission getPermissionById(Object id) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Retrieves all permissions defined in the system.
	 * 
	 * @return the names of all permissions defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	PermissionSet getAllPermissions() throws DataBackendException;

	/**
	 * Retrieves all non-disabled permissions defined in the system.
	 * 
	 * @return the names of all non-disabled permissions defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	PermissionSet getPermissions() throws DataBackendException;

	/**
	 * Creates a new permission with specified attributes.
	 * 
	 * @param permission
	 *            The object describing the permission to be created.
	 * @return the new Permission object.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws EntityExistsException
	 *             if the permission already exists.
	 */
	Permission addPermission(Permission permission)
			throws DataBackendException, EntityExistsException;

	/**
	 * Removes a Permission from the system.
	 * 
	 * @param permission
	 *            The object describing the permission to be removed.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the permission does not exist.
	 */
	void removePermission(Permission permission) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Disables a Permission (effectively rendering it as removed).
	 * 
	 * @param permission
	 *            The object describing the permission to be removed.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the permission does not exist.
	 */
	void disablePermission(Permission permission) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Renames an existing Permission.
	 * 
	 * @param permission
	 *            The object describing the permission to be renamed.
	 * @param name
	 *            the new name for the permission.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the permission does not exist.
	 */
	void renamePermission(Permission permission, String name)
			throws DataBackendException, UnknownEntityException;

	/**
	 * Determines if the <code>Permission</code> exists in the security
	 * system.
	 * 
	 * @param permission
	 *            a <code>Permission</code> value
	 * @return true if the permission exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one Permission with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	boolean checkExists(Permission permission) throws DataBackendException;

	/**
	 * Determines if a <code>Permission</code> exists in the security system
	 * with the specified name.
	 * 
	 * @param permissionName
	 *            the name of a <code>Permission</code> to check
	 * @return true if the permission exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one Permission with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	boolean checkExists(String permissionName) throws DataBackendException;
}
