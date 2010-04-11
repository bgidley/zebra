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

import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;

/**
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: GroupSetTest.java,v 1.1 2005/11/14 18:20:49 bgidley Exp $
 */
public class GroupSetTest extends TestCase
{

    /**
	 * Defines the testcase name for JUnit.
	 * 
	 * @param name the testcase's name.
	 */
    public GroupSetTest(String name)
    {
        super(name);
    }
    public static void main(String[] args)
    {
        junit.textui.TestRunner.run(GroupSetTest.class);
    }

    public void testNullGroup() throws Exception {
        GroupSet groupSet = new GroupSet();
        assertFalse(groupSet.contains(null));             
    }
    
    public void testAddGroups() throws Exception
    {
        Group group = new DynamicGroup();
        group.setId(new Integer(1));
        group.setName("Eric");
        GroupSet groupSet = new GroupSet();
        assertTrue(groupSet.add(group));
        assertFalse(groupSet.add(group));
        assertTrue(groupSet.contains(group));

        Group group2 = new DynamicGroup();
        group2.setName("Kate");
        group2.setId(new Integer(2));
        groupSet.add(group2);

        Group group3 = new DynamicGroup();
        group3.setId(new Integer(1));
        group3.setName("Eric");
        groupSet.add(group3);
        assertTrue(groupSet.contains(group));
        assertTrue(groupSet.contains((Object) group));
        assertTrue(groupSet.contains(group2));
        assertTrue(groupSet.contains(group3));
        assertTrue(groupSet.contains(group));
        
        Role role = new DynamicRole();
        role.setName("role");
        role.setId("role");
        try {
            groupSet.add(role);
            fail("Should have thrown ClassCastException");
        }
        catch (ClassCastException cce){
            assertTrue(cce.getMessage().indexOf("GroupSet")>-1);
        }
        try {
            ((SecuritySet)groupSet).add(role);
            fail("Should have thrown ClassCastException");
        }
        catch (ClassCastException cce){
            assertTrue(cce.getMessage().indexOf("GroupSet")>-1);
        }        
    }

    public void testGroupSetWithSubclass() throws Exception
    {
        GroupSet groupSet = new GroupSet();
        Group group = new GroupSubClass();
		group.setId(new Integer(1));
		group.setName("Eric");

        groupSet.add(group);
        assertTrue(groupSet.contains(group));

        Group group2 = new DynamicGroup();
        group2.setId(new Integer(1));
        group2.setName("Eric");
        assertTrue(groupSet.contains(group2));

    }

    class GroupSubClass extends DynamicGroup
    {
        private String extraGroupData;

        /**
		 * @return Returns the extraGroupData.
		 */
        public String getExtraGroupData()
        {
            return extraGroupData;
        }

        /**
		 * @param extraGroupData The extraGroupData to set.
		 */
        public void setExtraGroupData(String extraGroupData)
        {
            this.extraGroupData = extraGroupData;
        }

    }

}
