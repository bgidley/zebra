package com.anite.zebra.core.test;

/*
 * Copyright 2004/2005 Anite - Enforcement & Security
 *    http://www.anite.com/publicsector
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import java.util.Iterator;

import junit.framework.TestCase;

import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.MockTaskDefinitions;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;

/**
 * @author Eric.Pugh
 * @author Matthew Norris
 */
public class TaskDefinitionsTest extends TestCase {
	/**
	 * tests that the iterator works correctly
	 * @throws Exception
	 *
	 * @author Eric.Pugh
	 */
	public void testIterator() throws Exception {
		MockProcessDef pd = new MockProcessDef("");
	    MockTaskDefinitions td = (MockTaskDefinitions) pd.getTaskDefs();
	    td.add(new AutoRunTaskDef(pd,""));
	    td.add(new ManualRunTaskDef(pd,""));
	    Iterator i =td.iterator();
	    assertNotNull(i);
	    assertTrue(i.hasNext());
	    i.next();
	    assertTrue(i.hasNext());
	    i.next();
	    assertFalse(i.hasNext());

	}
	
	/**
	 * 
	 * tests to see if the ID generation is working in MOCK classes 
	 * 
	 * @throws Exception
	 * 
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 */
	public void testIDGen() throws Exception {
		
		MockProcessDef pd = new MockProcessDef("");
		MockProcessDef pd2 = new MockProcessDef("");
	    assertNotSame(pd.getId(),pd2.getId());
		MockTaskDef td1 = new MockTaskDef(pd,"");
	    MockTaskDef td2 = new MockTaskDef(pd,"");
	    assertNotSame(td1.getId(),td2.getId());
	    MockRouting mr1 = td1.addRoutingOut(td1);
	    MockRouting mr2 = td1.addRoutingOut(td1);
	    assertNotSame(mr1.getId(),mr2.getId());
	    
	}
	
	/**
	 * tests to see if the MOCK routing objects work 
	 * 
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @throws Exception
	 */
	public void testRouting() throws Exception {
		MockProcessDef pd = new MockProcessDef("testRouting");
		MockTaskDef task1 = new MockTaskDef(pd,"1");
		MockTaskDef task2 = new MockTaskDef(pd,"2");
		MockRouting mr = task1.addRoutingOut(task2);
		assertTrue(pd.getMockRoutingDefs().contains(mr));
		assertTrue(task2.getRoutingIn().contains(mr));
		assertTrue(task1.getRoutingOut().contains(mr));
		assertFalse(task1.getRoutingIn().contains(mr));
		
		
	}
}