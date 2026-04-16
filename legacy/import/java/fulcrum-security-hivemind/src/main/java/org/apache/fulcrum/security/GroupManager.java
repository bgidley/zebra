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
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.GroupSet;
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
 * @version $Id: GroupManager.java,v 1.2 2006/03/18 16:19:38 biggus_richus Exp $
 */
public interface GroupManager {
	/**
	 * Construct a blank Group object.
	 * 
	 * This method calls getGroupClass, and then creates a new object using the
	 * default constructor.
	 * 
	 * @return an object implementing Group interface.
	 * @throws DataBackendException
	 *             if the object could not be instantiated.
	 */
	Group getGroupInstance() throws DataBackendException;

	/**
	 * Construct a blank Group object.
	 * 
	 * This method calls getGroupClass, and then creates a new object using the
	 * default constructor.
	 * 
	 * @param groupName
	 *            The name of the Group
	 * 
	 * @return an object implementing Group interface.
	 * @throws DataBackendException
	 *             if the object could not be instantiated.
	 */
	Group getGroupInstance(String groupName) throws DataBackendException;

	/**
	 * Retrieve a Group object with specified name.
	 * 
	 * @param name
	 *            the name of the Group.
	 * @return an object representing the Group with specified name.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the group does not exist.
	 */
	Group getGroupByName(String name) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Retrieve a Group object with specified Id.
	 * 
	 * @param name
	 *            the name of the Group.
	 * 
	 * @return an object representing the Group with specified name.
	 * 
	 * @exception UnknownEntityException
	 *                if the permission does not exist in the database.
	 * @exception DataBackendException
	 *                if there is a problem accessing the storage.
	 */
	Group getGroupById(Object id) throws DataBackendException,
			UnknownEntityException, EntityDisabledException;

	/**
	 * Renames an existing Group.
	 * 
	 * @param group
	 *            The object describing the group to be renamed.
	 * @param name
	 *            the new name for the group.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the group does not exist.
	 */
	void renameGroup(Group group, String name) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Removes a Group from the system.
	 * 
	 * @param group
	 *            The object describing the group to be removed.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the group does not exist.
	 */
	void removeGroup(Group group) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Disables a Group (effectively rendering it as removed, but without
	 * actually removing it).
	 * 
	 * @param group
	 *            The object describing the group to be disabled.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws UnknownEntityException
	 *             if the group does not exist.
	 */
	void disableGroup(Group group) throws DataBackendException,
			UnknownEntityException;

	/**
	 * Creates a new group with specified attributes.
	 * 
	 * @param group
	 *            the object describing the group to be created.
	 * @return the new Group object.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 * @throws EntityExistsException
	 *             if the group already exists.
	 */
	Group addGroup(Group group) throws DataBackendException,
			EntityExistsException;

	/**
	 * Retrieves all groups defined in the system.
	 * 
	 * @return the names of all groups defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	GroupSet getAllGroups() throws DataBackendException;

	/**
	 * Retrieves all non-disabled groups defined in the system.
	 * 
	 * @return the names of all non-disabled groups defined in the system.
	 * @throws DataBackendException
	 *             if there was an error accessing the data backend.
	 */
	GroupSet getGroups() throws DataBackendException;

	/**
	 * Determines if the <code>Group</code> exists in the security system.
	 * 
	 * @param permission
	 *            a <code>Group</code> value
	 * @return true if the group exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one group with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	public boolean checkExists(Group group) throws DataBackendException;

	/**
	 * Determines if a <code>Group</code> exists in the security system with
	 * the specified name.
	 * 
	 * @param groupName
	 *            the name of a <code>Group</code> to check.
	 * @return true if the group exists in the system, false otherwise
	 * @throws DataBackendException
	 *             when more than one group with the same name exists.
	 * @throws Exception
	 *             A generic exception.
	 */
	public boolean checkExists(String group) throws DataBackendException;

}
