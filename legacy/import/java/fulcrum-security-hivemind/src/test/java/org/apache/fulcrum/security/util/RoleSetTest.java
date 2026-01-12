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

import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;

/**
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: RoleSetTest.java,v 1.1 2005/11/14 18:20:49 bgidley Exp $
 */
public class RoleSetTest extends TestCase
{

    /**
	 * Defines the testcase name for JUnit.
	 * 
	 * @param name the testcase's name.
	 */
    public RoleSetTest(String name)
    {
        super(name);
    }
    public static void main(String[] args)
    {
        junit.textui.TestRunner.run(RoleSetTest.class);
    }

    public void testNullRole() throws Exception {
        RoleSet roleSet = new RoleSet();
        assertFalse(roleSet.contains(null));             
    }
    
    public void testAddRoles() throws Exception
    {
        Role role = new DynamicRole();
        role.setId(new Integer(1));
        role.setName("Eric");
        RoleSet roleSet = new RoleSet();
        assertTrue(roleSet.add(role));
        assertTrue(roleSet.contains(role));

        Role role2 = new DynamicRole();
        role2.setName("Kate");
        role2.setId(new Integer(2));
        roleSet.add(role2);

        Role role3 = new DynamicRole();
        role3.setId(new Integer(1));
        role3.setName("Eric");
        roleSet.add(role3);
        assertTrue(roleSet.contains(role));
        assertTrue(roleSet.contains((Object) role));
        assertTrue(roleSet.contains(role2));
        assertTrue(roleSet.contains(role3));
        assertTrue(roleSet.contains(role));
    }

    public void testRoleSetWithSubclass() throws Exception
    {
        RoleSet roleSet = new RoleSet();
        Role role = new RoleSubClass();
		role.setId(new Integer(1));
		role.setName("Eric");

        roleSet.add(role);
        assertTrue(roleSet.contains(role));

        Role role2 = new DynamicRole();
        role2.setId(new Integer(1));
        role2.setName("Eric");
        assertTrue(roleSet.contains(role2));

    }

    class RoleSubClass extends DynamicRole
    {
        private String extraRoleData;

        /**
		 * @return Returns the extraRoleData.
		 */
        public String getExtraRoleData()
        {
            return extraRoleData;
        }

        /**
		 * @param extraRoleData The extraRoleData to set.
		 */
        public void setExtraRoleData(String extraRoleData)
        {
            this.extraRoleData = extraRoleData;
        }

    }

}
