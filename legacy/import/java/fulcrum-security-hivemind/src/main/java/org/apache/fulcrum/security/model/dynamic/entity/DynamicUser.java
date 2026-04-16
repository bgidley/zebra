package org.apache.fulcrum.security.model.dynamic.entity;

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

import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.entity.impl.SecurityEntityImpl;
import org.apache.fulcrum.security.util.GroupSet;

/**
 * Represents the "simple" model where permissions are related to roles, roles
 * are related to groups and groups are related to users, all in many to many
 * relationships.
 * 
 * Users have a set of delegates and delegatee's. If user A has B in their
 * delegates - B assumes A's groups,roles and permissions If user C has D in
 * their delegatees - C assumes D's groups,roles and permissions
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: DynamicUser.java,v 1.5 2006/07/19 09:15:17 bgidley Exp $
 */
public class DynamicUser extends SecurityEntityImpl implements User {
	private static final long serialVersionUID = -7298282701583455184L;

	private String password;

	private Date passwordExpiryDate;

	private long lockTime;

	private int loginAttempts;

	private List passwordHistory = new ArrayList<String>();

	private Set groupSet = new GroupSet();

	private Set delegators = new HashSet();

	private Set delegatees = new HashSet();

	/**
	 * 
	 * @return Returns the password history.
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public List getPasswordHistory() {
		return this.passwordHistory;
	}

	/**
	 * 
	 * @param passwordHistory
	 *            The password history to set.
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public void setPasswordHistory(List passwordHistory) {
		this.passwordHistory = passwordHistory;
	}

	/**
	 * @return Returns the delegatees.
	 */
	public Set getDelegatees() {
		return delegatees;
	}

	/**
	 * @param delegatees
	 *            The delegatees to set.
	 */
	public void setDelegatees(Set delegatees) {
		this.delegatees = delegatees;
	}

	/**
	 * @return Returns the delegators.
	 */
	public Set getDelegators() {
		return delegators;
	}

	/**
	 * @param delegates
	 *            The delegators to set.
	 */
	public void setDelegators(Set delegates) {
		this.delegators = delegates;
	}

	/**
	 * @return Returns the password.
	 */
	public String getPassword() {
		return password;
	}

	/**
	 * @param password
	 *            The password to set.
	 */
	public void setPassword(String password) {
		this.password = password;
	}

	/**
	 * 
	 * @return The expiry date of the current password.
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public Date getPasswordExpiryDate() {
		return passwordExpiryDate;
	}

	/**
	 * 
	 * @param passwordExpiryDate
	 *            Set the expiry date of the password.
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public void setPasswordExpiryDate(Date passwordExpiryDate) {
		this.passwordExpiryDate = passwordExpiryDate;
	}

	/**
	 * 
	 * @return Return whether the user is locked.
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public long getLockTime() {
		return lockTime;
	}

	/**
	 * 
	 * @param locked
	 *            Sets whether the user is locked
	 * 
	 * @author richard.brooks Created on Jan 11, 2006
	 */
	public void setLockTime(long lockTime) {
		this.lockTime = lockTime;
	}

	/**
	 * @return
	 */
	public GroupSet getGroups() {
		return new GroupSet(groupSet);
	}

	/**
	 * @param groups
	 */
	public void setGroups(GroupSet groups) {
		if (groups != null)
			this.groupSet = groups;
		else
			this.groupSet = new GroupSet();
	}

	public void removeGroup(Group group) {
		getGroups().remove(group);
	}

	public void addGroup(Group group) {
		getGroups().add(group);
	}

	public void setGroupsAsSet(Set groups) {
		this.groupSet = groups;
	}

	public Set getGroupsAsSet() {
		return groupSet;
	}

	public int getLoginAttempts() {
		return loginAttempts;
	}

	public void setLoginAttempts(int loginAttempts) {
		this.loginAttempts = loginAttempts;
	}
}