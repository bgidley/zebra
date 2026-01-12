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

import org.apache.fulcrum.security.AbstractSecurityServiceTest;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.UnknownEntityException;

/**
 * @author Eric Pugh
 *
 */
public abstract class AbstractGroupManagerTest extends AbstractSecurityServiceTest
{
    public void setUp() throws Exception{
        super.setUp();
    }
 
    /*
     * Class to test for Group getGroupInstance()
     */
    public void testGetGroupInstance() throws Exception
    {
        Group group = getGroupManager().getGroupInstance();
        assertNotNull(group);
        assertTrue(group.getName() == null);
    }
    
    /*
     * Class to test for Group getGroupInstance(String)
     */
    public void testGetGroupInstanceString() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("DOG_CATCHER");
        assertEquals("DOG_CATCHER".toLowerCase(), group.getName());
    }
    
    public void testGetGroup() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("DOG_CATCHER2");
        getGroupManager().addGroup(group);
        Group group2 = getGroupManager().getGroupByName("DOG_CATCHER2");
        assertEquals(group.getName(), group2.getName());
    }
    
    public void testGetGroupByName() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL");
        getGroupManager().addGroup(group);
        Group group2 = getGroupManager().getGroupByName("CLEAN_KENNEL");
        assertEquals(group.getName(), group2.getName());
        group2 = getGroupManager().getGroupByName("Clean_KeNNel");
        assertEquals(group.getName(), group2.getName());
    }
    
    public void testGetGroupById() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL_A");
        getGroupManager().addGroup(group);
        Group group2 = getGroupManager().getGroupById(group.getId());
        assertEquals(group.getName(), group2.getName());
    }
    
    public void testGetAllGroups() throws Exception
    {
        int size = getGroupManager().getAllGroups().size();
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL_J");
        getGroupManager().addGroup(group);
        GroupSet groupSet = getGroupManager().getAllGroups();
        assertEquals(size + 1, groupSet.size());
    }
    
    public void testRemoveGroup() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL_K");
        getGroupManager().addGroup(group);
        int size = getGroupManager().getAllGroups().size();
        if (group instanceof DynamicGroup)
        {
            assertEquals(0, ((DynamicGroup) group).getUsers().size());
            assertEquals(0, ((DynamicGroup) group).getRoles().size());
        }
        getGroupManager().removeGroup(group);
        try
        {
            getGroupManager().getGroupById(group.getId());
            fail("Should have thrown UEE");
        }
        catch (UnknownEntityException uee)
        {
            //good
        }
        assertEquals(size - 1, getGroupManager().getAllGroups().size());
    }
    
	public void testDisableGroup() throws Exception {
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL_L");
        getGroupManager().addGroup(group);
		getGroupManager().disableGroup(group);
		try {
			getGroupManager().getGroupByName(group.getName());
			fail("Should have thrown EntityDisabledException");
		} catch (EntityDisabledException ede) {
			// brilliant!
		}
		
		try {
			getGroupManager().addGroup(group);
			fail("Should have thrown EntityExistsException");
		} catch (EntityExistsException eee) {
			// brilliant!
		}
	}
    
    public void testRenameGroup() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("CLEAN_KENNEL_X");
        getGroupManager().addGroup(group);
        int size = getGroupManager().getAllGroups().size();
        getGroupManager().renameGroup(group, "CLEAN_GROOMING_ROOM");
        Group group2 = getGroupManager().getGroupById(group.getId());
        assertEquals("CLEAN_GROOMING_ROOM".toLowerCase(), group2.getName());
        assertEquals(size, getGroupManager().getAllGroups().size());
    }
    
    public void testCheckExists() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("GREET_PEOPLE");
        getGroupManager().addGroup(group);
        assertTrue(getGroupManager().checkExists(group));
        Group group2 = getGroupManager().getGroupInstance("WALK_DOGS");
        assertFalse(getGroupManager().checkExists(group2));
    }
    
    public void testCheckExistsWithString() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("GREET_PEOPLE2");
        getGroupManager().addGroup(group);
        assertTrue(getGroupManager().checkExists(group.getName()));
        Group group2 = getGroupManager().getGroupInstance("WALK_DOGS2");
        assertFalse(getGroupManager().checkExists(group2.getName()));
    }
    
    /*
     * Class to test for boolean checkExists(string)
     */
    public void testAddGroupTwiceFails() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("EATLUNCH");
        getGroupManager().addGroup(group);
        assertTrue(getGroupManager().checkExists(group.getName()));
        Group group2 = getGroupManager().getGroupInstance("EATLUNCH");
        try {
            getGroupManager().addGroup(group2);
        }
        catch (EntityExistsException uee){
            //good
        }
    }  
    
    public void testAddGroup() throws Exception
    {
        Group group = getGroupManager().getGroupInstance("CLEAN_RABBIT_HUTCHES");
        assertNull(group.getId());
        getGroupManager().addGroup(group);
        assertNotNull(group.getId());
        assertNotNull(getGroupManager().getGroupById(group.getId()));
    }

}
