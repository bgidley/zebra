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
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.RoleSet;
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
 * @version $Id: RoleManager.java,v 1.2 2006/03/18 16:19:38 biggus_richus Exp $
 */
public interface RoleManager {
	/** Avalon role - used to id the component within the manager */
	String ROLE = RoleManager.class.getName();

	/**
	 * Construct a blank Role object.
	 * 
	 * This method calls getRoleClass, and then creates a new object using the
	 * default constructor.
	 * 
	 * @return an object implementing Role interface.
	 * @throws DataBackendException
	 *             if the object could not be instantiated.
	 */
	public Role getRoleInstance() throws DataBackendException;

	/**
	 * Construct a blank Role object.
	 * 
	 * This method calls getRoleClass, and then creates a new object using the
	 * default constructor.
	 * 
	 * @param roleName
	 *            The name of the Role
	 * 
	 * @return an object implementing Role interface.
	 * @throws DataBackendException
	 *             if the object could not be instantiated.
	 */
	Role getRoleInstance(String roleName) throws DataBackendException;

	/**
	 * Retrieve a Role object with specified name.
	 * 
	 * @param name
	 *            the name of the Role.
	 * @return an object representing the Role with specified name.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the role does not exist.
	 */
	Role getRoleByName(String name) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Retrieve a Role object with specified Id.
	 * 
	 * @param name
	 *            the name of the Role.
	 * 
	 * @return an object representing the Role with specified name.
	 * 
	 * @exception UnknownEntityException
	 *                if the permission does not exist in the database.
	 * @exception DataBackendException
	 *                if there is a problem accessing the storage.
	 */
	Role getRoleById(Object id) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Retrieves all roles defined in the system.
	 * 
	 * @return the names of all roles defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	RoleSet getAllRoles() throws DataBackendException;

	/**
	 * Retrieves all non-disabled roles defined in the system.
	 * 
	 * @return the names of all non-disabled roles defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	RoleSet getRoles() throws DataBackendException;

	/**
	 * Creates a new role with specified attributes.
	 * 
	 * @param role
	 *            The object describing the role to be created.
	 * @return the new Role object.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws EntityExistsException
	 *             if the role already exists.
	 */
	Role addRole(Role role) throws DataBackendException, EntityExistsException;

	/**
	 * Removes a Role from the system.
	 * 
	 * @param role
	 *            The object describing the role to be removed.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the role does not exist.
	 */
	void removeRole(Role role) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Disables a Role (effectively rendering it as removed).
	 * 
	 * @param role
	 *            The object describing the role to be disabled.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the role does not exist.
	 */
	void disableRole(Role role) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Renames an existing Role.
	 * 
	 * @param role
	 *            The object describing the role to be renamed.
	 * @param name
	 *            the new name for the role.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the role does not exist.
	 */
	void renameRole(Role role, String name) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Determines if the <code>Role</code> exists in the security system.
	 * 
	 * @param role
	 *            a <code>Role</code> value
	 * @return true if the role exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one Role with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	boolean checkExists(Role role) throws DataBackendException;

	/**
	 * Determines if a <code>Role</code> exists in the security system with
	 * the specified role name.
	 * 
	 * @param roleName
	 *            the name of a <code>Role</code> to check.
	 * @return true if the role exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one Role with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	boolean checkExists(String roleName) throws DataBackendException;
}
