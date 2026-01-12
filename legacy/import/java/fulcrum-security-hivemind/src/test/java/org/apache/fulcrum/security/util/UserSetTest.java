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

import junit.framework.TestCase;

import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
/**
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: UserSetTest.java,v 1.1 2005/11/14 18:20:49 bgidley Exp $
 */
public class UserSetTest extends TestCase
{

    /**
	 * Defines the testcase name for JUnit.
	 * 
	 * @param name the testcase's name.
	 */
    public UserSetTest(String name)
    {
        super(name);
    }
    public static void main(String[] args)
    {
        junit.textui.TestRunner.run(UserSetTest.class);
    }

    public void testAddUsers() throws Exception
    {
        User user = new DynamicUser();
        user.setId(new Integer(1));
        user.setName("Eric");
        UserSet userSet = new UserSet();
        userSet.add(user);
        assertTrue(userSet.contains(user));

        User user2 = new DynamicUser();
        user2.setName("Kate");
        user2.setId(new Integer(2));
        userSet.add(user2);

        User user3 = new DynamicUser();
        user3.setId(new Integer(1));
        user3.setName("Eric");
        assertTrue(userSet.contains(user));
        assertTrue(userSet.contains((Object) user));
        assertTrue(userSet.contains(user2));
        assertTrue(userSet.contains(user3));
		assertTrue(userSet.contains(user));

    }

}
