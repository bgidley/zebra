package org.apache.fulcrum.security.model.test;

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

import java.util.GregorianCalendar;
import java.util.List;

import org.apache.fulcrum.security.AbstractSecurityServiceTest;
import org.apache.fulcrum.security.acl.AccessControlList;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PasswordExpiredException;
import org.apache.fulcrum.security.util.PasswordHistoryException;
import org.apache.fulcrum.security.util.PasswordMismatchException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.fulcrum.security.util.UserLockedException;
import org.apache.fulcrum.security.util.UserSet;

/**
 * @author Eric Pugh
 * 
 * To change the template for this generated type comment go to
 * Window>Preferences>Java>Code Generation>Code and Comments
 */
public abstract class AbstractUserManagerTest extends
		AbstractSecurityServiceTest {

	public void testCheckExists() throws Exception {
		User user = getUserManager().getUserInstance("Philipa");
		getUserManager().addUser(user, "bobo");
		assertTrue(getUserManager().checkExists("philipa"));
		assertTrue(getUserManager().checkExists(user));
		assertFalse(getUserManager().checkExists("ImaginaryFriend"));
		user = getUserManager().getUserInstance("ImaginaryFriend");
		assertFalse(getUserManager().checkExists(user));
	}

	public void testCheckExistsWithString() throws Exception {
		User user = getUserManager().getUserInstance("Philip2");
		getUserManager().addUser(user, "bobo");
		assertTrue(getUserManager().checkExists("philip2"));
		assertTrue(getUserManager().checkExists(user.getName()));
		assertFalse(getUserManager().checkExists("ImaginaryFriend2"));
		user = getUserManager().getUserInstance("ImaginaryFriend2");
		assertFalse(getUserManager().checkExists(user.getName()));
	}

	/*
	 * Class to test for User retrieve(String)
	 */
	public void testGetUserString() throws Exception {
		User user = getUserManager().getUserInstance("QuietMike");
		getUserManager().addUser(user, "bobo");
		user = getUserManager().getUser("QuietMike");
		assertNotNull(user);
	}

	public void testGetUserById() throws Exception {
		User user = getUserManager().getUserInstance("QuietMike2");
		getUserManager().addUser(user, "bobo");
		User user2 = getUserManager().getUserById(user.getId());
		assertEquals(user.getName(), user2.getName());
		assertEquals(user.getId(), user2.getId());
	}

	/*
	 * Class to test for User retrieve(String, String)
	 */
	public void testGetUserStringString() throws Exception {
		User user = getUserManager().getUserInstance("Richard");
		getUserManager().addUser(user, "va");
		user = getUserManager().getUser("Richard", "va");
		assertNotNull(user);
		user = getUserManager().getUser("richard", "va");
		assertNotNull(user);
		try {
			user = getUserManager().getUser("richard", "VA");
			fail("should have thrown PasswordMismatchException");
		} catch (PasswordMismatchException pme) {
			// good
		}

		// Simulate password expiry
		GregorianCalendar gc = new GregorianCalendar(1974, 4, 25);
		user.setLockTime(gc.getTimeInMillis());
		user.setPasswordExpiryDate(gc.getTime());
		try {
			getUserManager().getUser("richard", "va");
			fail("Should have thrown PasswordExpiredException");
		} catch (PasswordExpiredException ule) {
			//good
		}
	}

	public void testGetAllUsers() throws Exception {
		int size = getUserManager().getAllUsers().size();
		User user = getUserManager().getUserInstance("Bob");
		getUserManager().addUser(user, "");
		UserSet userSet = getUserManager().getAllUsers();
		assertEquals(size + 1, userSet.size());
	}

	public void testAuthenticate() throws Exception {
		User user = getUserManager().getUserInstance("Kay");
		getUserManager().addUser(user, "jc");
		getUserManager().authenticate(user, "jc");
		try {
			getUserManager().authenticate(user, "JC");
			fail("should have thrown PasswordMismatchException");
		} catch (PasswordMismatchException pme) {
			// good - first permitted attempt
		}
		
		try {
			getUserManager().authenticate(user, "JC");
			fail("should have thrown PasswordMismatchException");
		} catch (PasswordMismatchException pme) {
			// good - second permitted attempt
		}

		try {
			getUserManager().authenticate(user, "JC");
			fail("should have thrown PasswordMismatchException");
		} catch (PasswordMismatchException pme) {
			// good - third permitted attempt
		}

		try {
			getUserManager().authenticate(user, "jc");
			fail("Should have thrown UserLockedException");
		} catch (UserLockedException ule) {
			//good - user is now locked
		}
		
		// Simulate enough time passing since user was locked
		GregorianCalendar gc = new GregorianCalendar(1974, 4, 25);
		user.setLockTime(gc.getTimeInMillis());
		getUserManager().authenticate(user, "jc");
	}

	@SuppressWarnings("unchecked")
	public void testChangePassword() throws Exception {
		User user = getUserManager().getUserInstance("Jonathan");
		getUserManager().addUser(user, "one");
		try {
			getUserManager().changePassword(user, "WrongPWD", "two");
			fail("should have thrown PasswordMismatchException");
		} catch (PasswordMismatchException pme) {
			// good
		}
		getUserManager().changePassword(user, "one", "six");
		getUserManager().authenticate(user, "six");
		try {
			getUserManager().changePassword(user, "six", "one");
			fail("Should have thrown PasswordHistoryException");
		} catch (PasswordHistoryException phe) {
			// good
		}

		List passwordHistory = user.getPasswordHistory();
		passwordHistory.add("two");
		passwordHistory.add("three");
		passwordHistory.add("four");
		passwordHistory.add("five");
		try {
			getUserManager().changePassword(user, "six", "one");
			fail("Should have thrown PasswordHistoryException");
		} catch (PasswordHistoryException phe) {
			// good
		}
		getUserManager().changePassword(user, "six", "seven");
		getUserManager().changePassword(user, "seven", "one");
		getUserManager().authenticate(user, "one");
		getUserManager().changePassword(user, "one", "ninety-nine");
	}

	public void testForcePassword() throws Exception {
		User user = getUserManager().getUserInstance("Connor");
		getUserManager().addUser(user, "jc_subset");
		getUserManager().forcePassword(user, "JC_SUBSET");
		getUserManager().authenticate(user, "JC_SUBSET");
	}

	/*
	 * Class to test for User getUserInstance()
	 */
	public void testGetUserInstance() throws Exception {
		User user = getUserManager().getUserInstance();
		assertNotNull(user);
		assertTrue(user.getName() == null);
	}

	/*
	 * Class to test for User getUserInstance(String)
	 */
	public void testGetUserInstanceString() throws Exception {
		User user = getUserManager().getUserInstance("Philip");
		assertEquals("philip", user.getName());
	}

	/**
	 * Need to figure out if save is something we want.. right now it just bloes
	 * up if you actually cahnge anything.
	 * 
	 * @todo figur out what to do here...
	 * @throws Exception
	 */
	public void testSaveUser() throws Exception {
		User user = getUserManager().getUserInstance("Kate");
		getUserManager().addUser(user, "katiedid");
		user = getUserManager().getUser(user.getName());
		// user.setName("Katherine");
		getUserManager().saveUser(user);
		assertEquals("kate", getUserManager().getUser(user.getName()).getName());
	}

	public void testGetACL() throws Exception {
		User user = getUserManager().getUserInstance("Tony");
		getUserManager().addUser(user, "california");
		AccessControlList acl = getUserManager().getACL(user);
		assertNotNull(acl);
	}

	public void testDisableUser() throws Exception {
		User user = getUserManager().getUserInstance("Dave");
		getUserManager().addUser(user, "scottysaywhat");
		getUserManager().disableUser(user);
		try {
			getUserManager().getUser(user.getName());
			fail("Should have thrown EntityDisabledException");
		} catch (EntityDisabledException ede) {
			// brilliant!
		}
		
		try {
			getUserManager().addUser(user, "scottyzip");
			fail("Should have thrown EntityExistsException");
		} catch (EntityExistsException eee) {
			// brilliant!
		}
	}
	
	public void testRemoveUser() throws Exception {
		User user = getUserManager().getUserInstance("Rick");
		getUserManager().addUser(user, "nb");
		getUserManager().removeUser(user);
		try {
			getUserManager().getUser(user.getName());
			fail("Should have thrown UEE");
		} catch (UnknownEntityException uee) {
			// good
		}
	}

	public void testAddUser() throws Exception {
		User user = getUserManager().getUserInstance("Joe1");
		assertNull(user.getId());
		getUserManager().addUser(user, "mc");
		user = getUserManager().getUserInstance("Joe2");
		assertNull(user.getId());
		getUserManager().addUser(user, "mc");
		assertNotNull(user.getId());
		assertNotNull(getUserManager().getUser(user.getName()));
	}

	/*
	 * Class to test for boolean checkExists(string)
	 */
	public void testAddUserTwiceFails() throws Exception {
		User user = getUserManager().getUserInstance("EATLUNCH");
		getUserManager().addUser(user, "bob");
		assertTrue(getUserManager().checkExists(user.getName()));
		User user2 = getUserManager().getUserInstance("EATLUNCH");
		try {
			getUserManager().addUser(user2, "bob");
		} catch (EntityExistsException uee) {
			// good
		}
		try {
			getUserManager().addUser(user2, "differentpassword");
		} catch (EntityExistsException uee) {
			// good
		}
	}

	public void testCheckUserCaseSensitiveExists() throws Exception {
		User user = getUserManager().getUserInstance("borrisJohnson");
		getUserManager().addUser(user, "bob");

		assertTrue(getUserManager().checkExists("borrisJohnson"));
	}

}
