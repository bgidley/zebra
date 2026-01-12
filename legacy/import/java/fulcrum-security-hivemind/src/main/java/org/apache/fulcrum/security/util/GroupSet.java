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

import org.apache.fulcrum.security.entity.Group;

/**
 * This class represents a set of Groups. It's useful for building
 * administration UI. It enforces that only Group objects are allowed in the set
 * and only relevant methods are available.
 * 
 * @author <a href="mailto:john.mcnally@clearink.com">John D. McNally</a>
 * @author <a href="mailto:bmclaugh@algx.net">Brett McLaughlin</a>
 * @author <a href="mailto:marco@intermeta.de">Marco Kn&uuml;ttel</a>
 * @author <a href="mailto:hps@intermeta.de">Henning P. Schmiedehausen</a>
 * @version $Id: GroupSet.java,v 1.3 2006/07/19 09:15:16 bgidley Exp $
 */
public class GroupSet extends SecuritySet {
	private static final long serialVersionUID = 6882240173053961011L;

	/**
	 * Constructs an empty GroupSet
	 */
	public GroupSet() {
		super();
	}

	/**
	 * Constructs a new GroupSet with specified contents.
	 * 
	 * If the given collection contains multiple objects that are identical WRT
	 * equals() method, some objects will be overwritten.
	 * 
	 * @param groups
	 *            A collection of groups to be contained in the set.
	 */
	public GroupSet(Set groups) {
		this.wrappedSet=groups;
	}

	/**
	 * Adds a Group to this GroupSet.
	 * 
	 * @param group
	 *            A Group.
	 * @return True if Group was added; false if GroupSet already contained the
	 *         Group.
	 */
	@SuppressWarnings("unchecked")
	public boolean add(Group group) {
		return wrappedSet.add(group);

	}

	/**
	 * Adds a Group to this GroupSet.
	 * 
	 * @param obj
	 *            A Group.
	 * @return True if Group was added; false if GroupSet already contained the
	 *         Group.
	 */
	public boolean add(Object obj) {
		if (obj instanceof Group) {
			return add((Group) obj);
		} else {
			throw new ClassCastException(
					"Object passed to add to GroupSet is not of type Group");
		}
	}

	/**
	 * Adds the Groups in a Collection to this GroupSet.
	 * 
	 * @param groups
	 *            A Collection of Groups.
	 * @return True if this GroupSet changed as a result; false if no change to
	 *         this GroupSet occurred (this GroupSet already contained all
	 *         members of the added GroupSet).
	 */
	public boolean add(Collection groups) {
		boolean res = false;
		for (Iterator it = groups.iterator(); it.hasNext();) {
			Group g = (Group) it.next();
			res |= add(g);
		}
		return res;
	}

	/**
	 * Adds the Groups in another GroupSet to this GroupSet.
	 * 
	 * @param groupSet
	 *            A GroupSet.
	 * @return True if this GroupSet changed as a result; false if no change to
	 *         this GroupSet occurred (this GroupSet already contained all
	 *         members of the added GroupSet).
	 */
	public boolean add(GroupSet groupSet) {
		boolean res = false;
		for (Iterator it = groupSet.iterator(); it.hasNext();) {
			Group g = (Group) it.next();
			res |= add(g);
		}
		return res;
	}

	/**
	 * Removes a Group from this GroupSet.
	 * 
	 * @param group
	 *            A Group.
	 * @return True if this GroupSet contained the Group before it was removed.
	 */
	public boolean remove(Group group) {
		return super.remove(group);
	}

	/**
	 * Checks whether this GroupSet contains a Group.
	 * 
	 * @param group
	 *            A Group.
	 * @return True if this GroupSet contains the Group, false otherwise.
	 */
	public boolean contains(Group group) {
		return super.contains(group);
	}

	/**
	 * Returns a Group with the given name, if it is contained in this GroupSet.
	 * 
	 * @param groupName
	 *            Name of Group.
	 * @return Group if argument matched a Group in this GroupSet; null if no
	 *         match.
	 */
	public Group getGroupByName(String groupName) {
		return (Group) getByName(groupName);
	}

	/**
	 * Returns a Group with the given id, if it is contained in this GroupSet.
	 * 
	 * @param groupId
	 *            Id of the group
	 * @return Group if argument matched a Group in this GroupSet; null if no
	 *         match.
	 */
	public Group getGroupById(Object groupId) {
		return (Group) ((groupId != null) ? super.getById(groupId) : null);
	}

	/**
	 * Returns an Array of Groups in this GroupSet.
	 * 
	 * @return An Array of Group objects.
	 */
	@SuppressWarnings("unchecked")
	public Group[] getGroupsArray() {
		return (Group[]) getSet().toArray(new Group[0]);
	}

	/**
	 * Print out a GroupSet as a String
	 * 
	 * @returns The Group Set as String
	 * 
	 */
	public String toString() {
		StringBuffer sb = new StringBuffer();
		sb.append("GroupSet: ");

		for (Iterator it = iterator(); it.hasNext();) {
			Group g = (Group) it.next();
			sb.append('[');
			sb.append(g.getName());
			sb.append(" -> ");
			sb.append(g.getId());
			sb.append(']');
			if (it.hasNext()) {
				sb.append(", ");
			}
		}

		return sb.toString();
	}

}
