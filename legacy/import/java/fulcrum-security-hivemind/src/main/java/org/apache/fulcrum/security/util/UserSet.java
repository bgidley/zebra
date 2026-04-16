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

import org.apache.fulcrum.security.entity.User;

/**
 * This class represents a set of Users.  It is based on UserSet.
 * Hibernate doesn't return the right kind of set, so this is used to
 * force the type of set.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: UserSet.java,v 1.3 2006/07/19 09:15:16 bgidley Exp $
 */
public class UserSet
        extends SecuritySet
{
	private static final long serialVersionUID = 4415634631270197073L;

	/**
     * Constructs an empty UserSet
     */
    public UserSet()
    {
        super();
    }

    /**
     * Constructs a new UserSet with specified contents.
     *
     * If the given collection contains multiple objects that are
     * identical WRT equals() method, some objects will be overwritten.
     *
     * @param users A collection of users to be contained in the set.
     */
    public UserSet(Set users)
    {
    	this.wrappedSet = users;
    }

    /**
     * Adds a User to this UserSet.
     *
     * @param user A User.
     * @return True if User was added; false if UserSet already
     * contained the User.
     */
    @SuppressWarnings("unchecked")
	public boolean add(User user)
    {
    	return wrappedSet.add(user);
    }
    
    /**
     * Adds a User to this UserSet.
     *
     * @param obj A User.
     * @return True if User was added; false if UserSet already
     * contained the User.
     */
    public boolean add(Object obj) {
        if(obj instanceof User){
            return add((User)obj);
        }
        else {
            throw new ClassCastException("Object passed to add to UserSet is not of type User");
        }
    }     

    /**
     * Adds the Users in a Collection to this UserSet.
     *
     * @param users A Collection of Users.
     * @return True if this UserSet changed as a result; false
     * if no change to this UserSet occurred (this UserSet
     * already contained all members of the added UserSet).
     */
    public boolean add(Collection users)
    {
        boolean res = false;
        for (Iterator it = users.iterator(); it.hasNext();)
        {
            User r = (User) it.next();
            res |= add(r);
        }
        return res;
    }

    /**
     * Adds the Users in another UserSet to this UserSet.
     *
     * @param userSet A UserSet.
     * @return True if this UserSet changed as a result; false
     * if no change to this UserSet occurred (this UserSet
     * already contained all members of the added UserSet).
     */
    public boolean add(UserSet userSet)
    {
        boolean res = false;
        for( Iterator it = userSet.iterator(); it.hasNext();)
        {
            User r = (User) it.next();
            res |= add(r);
        }
        return res;
    }

    /**
     * Removes a User from this UserSet.
     *
     * @param user A User.
     * @return True if this UserSet contained the User
     * before it was removed.
     */
    public boolean remove(User user)
    {
    	return wrappedSet.remove(user);
    	
    }

    /**
     * Checks whether this UserSet contains a User based on the
     * name of the User.
     *
     * @param user A User.
     * @return True if this UserSet contains the User,
     * false otherwise.
     */
    public boolean contains(User user)
    {
		return super.contains(user);
    }


    /**
     * Returns a User with the given name, if it is contained in
     * this UserSet.
     *
     * @param userName Name of User.
     * @return User if argument matched a User in this
     * UserSet; null if no match.
     */
    public User getUserByName(String userName)
    {
        return (User)getByName(userName);
        /*
		userName=userName.toLowerCase();
        return (StringUtils.isNotEmpty(userName))
                ? (User) nameMap.get(userName) : null;
                */
    }

    /**
     * Returns a User with the given id, if it is contained in this
     * UserSet.
     *
     * @param userId id of the User.
     * @return User if argument matched a User in this UserSet; null
     * if no match.
     */
    public User getUserById(Object userId)
    {
        return (userId != null) 
                ? (User) super.getById(userId) : null;
    }

    /**
     * Returns an Array of Users in this UserSet.
     *
     * @return An Array of User objects.
     */
    @SuppressWarnings("unchecked")
	public User[] getUsersArray()
    {
        return (User[]) getSet().toArray(new User[0]);
    }

    /**
     * Print out a UserSet as a String
     *
     * @returns The User Set as String
     *
     */
    public String toString()
    {
        StringBuffer sb = new StringBuffer();
        sb.append("UserSet: ");

        for(Iterator it = iterator(); it.hasNext();)
        {
            User r = (User) it.next();
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
