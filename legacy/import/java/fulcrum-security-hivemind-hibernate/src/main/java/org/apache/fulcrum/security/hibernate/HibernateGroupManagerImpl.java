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

import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.spi.AbstractGroupManager;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.hibernate.HibernateException;
import org.hibernate.Query;

/**
 * This implementation persists to a database via Hibernate.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: HibernateGroupManagerImpl.java,v 1.2 2006/03/18 16:18:21 biggus_richus Exp $
 */
public class HibernateGroupManagerImpl extends AbstractGroupManager {
    private PersistenceHelper persistenceHelper;

    /**
     * Retrieve a Group object with specified name.
     *
     * @param name the name of the Group.
     * @return an object representing the Group with specified name.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     * @throws UnknownEntityException if the group does not exist.
     */
    public Group getGroupByName(String name) throws DataBackendException, UnknownEntityException, EntityDisabledException {
        Group group = null;
        try {

            Query groupsQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName()+ " g where g.name=:name");
            groupsQuery.setString("name", name.toLowerCase());

            List groups = groupsQuery.list();
            if (groups.size() == 0) {
                throw new UnknownEntityException("Could not find group" + name);
            }
            group = (Group) groups.get(0);
            if (group.isDisabled()) {
            	throw new EntityDisabledException("Group is unavailable");
            }
     } catch (HibernateException e) {
            throw new DataBackendException("Error retriving group information", e);
        }
        return group;
    }

    /**
     * Retrieves all groups defined in the system.
     *
     * @return the names of all groups defined in the system.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     */
    public GroupSet getAllGroups() throws DataBackendException {
        GroupSet groupSet = new GroupSet();
        try {

            Query groupsQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + "");
            List groups = groupsQuery.list();
            groupSet.add(groups);
        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving group information", e);
        }
        return groupSet;
    }

    /**
     * Retrieves all non-disabled groups defined in the system.
     *
     * @return the names of all groups defined in the system.
     * @throws DataBackendException if there was an error accessing the
     *         data backend.
     */
    public GroupSet getGroups() throws DataBackendException {
        GroupSet groupSet = new GroupSet();
        try {

            Query groupsQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + " g where g.disabled = false");
            List groups = groupsQuery.list();
            groupSet.add(groups);
        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving group information", e);
        }
        return groupSet;
    }

    /**
     * Removes a Group from the system.
     *
     * @param group The object describing the group to be removed.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the group does not exist.
     */
    public synchronized void removeGroup(Group group) throws DataBackendException, UnknownEntityException {
        getPersistenceHelper().removeEntity(group);
    }
    
    /**
     * Disables a Group (effectively rendering it as removed, but without actually removing it).
     *
     * @param group The object describing the group to be disabled.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the group does not exist.
     */
    public synchronized void disableGroup(Group group) throws DataBackendException, UnknownEntityException {
        getPersistenceHelper().disableEntity(group);
    }
    

    /**
     * Renames an existing Group.
     *
     * @param group The object describing the group to be renamed.
     * @param name the new name for the group.
     * @throws DataBackendException if there was an error accessing the data
     *         backend.
     * @throws UnknownEntityException if the group does not exist.
     */
    public synchronized void renameGroup(Group group, String name) throws DataBackendException, UnknownEntityException {
        boolean groupExists = false;
        groupExists = checkExists(group);
        if (groupExists) {
            group.setName(name);
            getPersistenceHelper().updateEntity(group);
        } else {
            throw new UnknownEntityException("Unknown group '" + group + "'");
        }
    }

    /**
     * Determines if the <code>Group</code> exists in the security system.
     *
     * @param groupName a <code>Group</code> value
     * @return true if the group name exists in the system, false otherwise
     * @throws DataBackendException when more than one Group with
     *         the same name exists.
     */
    public boolean checkExists(String groupName) throws DataBackendException {
        List groups;
        try {

            Query groupsQuery = getPersistenceHelper().retrieveSession().createQuery(
                    "from " + getClassName() + " sg where sg.name=:name");

            groupsQuery.setString("name", groupName);

            groups = groupsQuery.list();
        } catch (HibernateException e) {
            throw new DataBackendException("Error retriving user information", e);
        }
        if (groups.size() > 1) {
            throw new DataBackendException("Multiple groups with same name '" + groupName + "'");
        }
        return (groups.size() == 1);
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
    protected synchronized Group persistNewGroup(Group group) throws DataBackendException {

        getPersistenceHelper().addEntity(group);
        return group;
    }

    /**
     * @return Returns the persistenceHelper.
     */
    public PersistenceHelper getPersistenceHelper() throws DataBackendException {

        return persistenceHelper;
    }

    /**
     * Retrieve a Group object with specified id.
     * 
     * @param id
     *            the id of the Group.
     * @return an object representing the Group with specified id.
     * @throws DataBackendException
     *             if there was an error accessing the data backend.
     * @throws UnknownEntityException
     *             if the group does not exist.
     */
public Group getGroupById(Object id) throws DataBackendException, UnknownEntityException, EntityDisabledException {

        Group group = null;

        if (id != null)
            try {
                Query groupsQuery =getPersistenceHelper().retrieveSession().createQuery(
                        "from " + getClassName() + " sr where sr.id=:id");
                
                groupsQuery.setLong("id", (Long) id);
                
                List groups =groupsQuery.list(); 
                if (groups.size() == 0) {
                    throw new UnknownEntityException("Could not find group by id " + id);
                }
                group = (Group) groups.get(0);
                
                if (group.isDisabled()) {
                	throw new EntityDisabledException("Group is unavailable");
                }
            } catch (HibernateException e) {
                throw new DataBackendException("Error retriving group information", e);
            }

        return group;
    }
    public void setPersistenceHelper(PersistenceHelper persistenceHelper) {
        this.persistenceHelper = persistenceHelper;
    }

}