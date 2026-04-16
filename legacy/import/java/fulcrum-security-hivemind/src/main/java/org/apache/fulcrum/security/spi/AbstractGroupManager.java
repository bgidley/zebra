package org.apache.fulcrum.security.spi;
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
import org.apache.commons.lang.StringUtils;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * This implementation keeps all objects in memory.  This is mostly meant to help
 * with testing and prototyping of ideas.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: AbstractGroupManager.java,v 1.2 2006/03/18 16:19:37 biggus_richus Exp $
 */
public abstract class AbstractGroupManager
    extends AbstractEntityManager
    implements GroupManager {
    protected abstract Group persistNewGroup(Group group) throws DataBackendException;

    /**
    * Construct a blank Group object.
    *
    * This method calls getGroupClass, and then creates a new object using
    * the default constructor.
    *
    * @return an object implementing Group interface.
    * @throws DataBackendException if the object could not be instantiated.
    */
    public Group getGroupInstance() throws DataBackendException {
        Group group;
        try {
            group = (Group) Class.forName(getClassName()).newInstance();
        }
        catch (Exception e) {
            throw new DataBackendException(
                "Problem creating instance of class " + getClassName(),
                e);
        }

        return group;
    }
    /**
    	* Construct a blank Group object.
    	*
    	* This method calls getGroupClass, and then creates a new object using
    	* the default constructor.
    	*
    	* @param groupName The name of the Group
    	*
    	* @return an object implementing Group interface.
    	*
    	* @throws DataBackendException if the object could not be instantiated.
    	*/
    public Group getGroupInstance(String groupName) throws DataBackendException {
        Group group = getGroupInstance();
        group.setName(groupName);
        return group;
    }

    /**
     * Retrieve a Group object with specified name.
     *
     * @param name the name of the Group.
     * @return an object representing the Group with specified name.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     * @throws UnknownEntityException if the group does not exist.
     */
    public Group getGroupByName(String name)
        throws DataBackendException, UnknownEntityException, EntityDisabledException {
        Group group = getAllGroups().getGroupByName(name);
        
        if (group == null) {
            throw new UnknownEntityException("The specified group does not exist");
        }
        
        if (group.isDisabled()) {
        	throw new EntityDisabledException("Group is disabled");
        }
        
        return group;
    }
    /**
     * Retrieve a Group object with specified Id.
     *
     * @param name the name of the Group.
     *
     * @return an object representing the Group with specified name.
     *
     * @throws UnknownEntityException if the permission does not
     *            exist in the database.
     * @throws DataBackendException if there is a problem accessing the
     *            storage.
     */
    public Group getGroupById(Object id)
        throws DataBackendException, UnknownEntityException, EntityDisabledException {
        Group group = getAllGroups().getGroupById(id);
        if (group == null) {
            throw new UnknownEntityException("The specified group does not exist");
        }
        
        if (group.isDisabled()) {
        	throw new EntityDisabledException("Group is disabled");
        }
        
        return group;
    }

    /**
    	* Creates a new group with specified attributes.
    	*
    	* @param group the object describing the group to be created.
    	* @return a new Group object that has id set up properly.
    	* @throws DataBackendException if there was an error accessing the data
    	*         backend.
    	* @throws EntityExistsException if the group already exists.
    	*/
    public synchronized Group addGroup(Group group)
        throws DataBackendException, EntityExistsException {
        if (StringUtils.isEmpty(group.getName())) {
            throw new DataBackendException("Could not create a group with empty name!");
        }

        if (checkExists(group)) {
	        throw new EntityExistsException(
	                "Group '" + group + "' is unavailable");
        }

        return persistNewGroup(group);
    }
    
    /**
	* Check whether a specified group exists.
	*
	* The name is used for looking up the group
	*
	* @param role The group to be checked.
	* @return true if the specified group exists
	* @throws DataBackendException if there was an error accessing
	*         the data backend.
	*/
	public boolean checkExists(Group group) throws DataBackendException	{
	    return checkExists(group.getName());
	}      

}
