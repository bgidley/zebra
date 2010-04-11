/*
 * Copyright 2005 Anite - Central Government Division
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

package com.anite.zebra.core.test;

import com.anite.zebra.core.MockEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

import junit.framework.TestCase;

/**
 * @author Matthew.Norris
 * Created on Sep 25, 2005
 */
public class SplitJoinWithNoParallelTest extends TestCase {

	/**
	 * 
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	private static final String ROUTE_END = "End";
	/**
	 * 
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	private static final String ROUTE_RESPAWN = "respawn";

	/**
	 * 
	 * Tests a split workflow where one route is marked non-parallel
	 * 
	 * 
	 * @throws Exception
	 *
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	public void testSplitJoinWithNoParallel() throws Exception {
		MockProcessDef pd = new MockProcessDef("");
		AutoRunTaskDef startDef = new AutoRunTaskDef(pd,"Start");
		
		ManualRunTaskDef splitDef = new ManualRunTaskDef(pd,"Splitter");
		pd.setFirstTask(startDef);
		startDef.addRoutingOut(splitDef);
		
		// parallel route straight back to the splitter task
		MockRouting mrParallel = splitDef.addRoutingOut(splitDef);
		mrParallel.setParallel(true);
		mrParallel.setName(ROUTE_RESPAWN);
		
		ManualRunTaskDef serialDef = new ManualRunTaskDef(pd,"Serial");
		MockRouting mrSerial = splitDef.addRoutingOut(serialDef);
		/*
		 *  has the same name as the parallel routing
		 *  this ensures that BOTH execute when the 
		 *  conditionaction property of the splitter task 
		 *  instance is set to "respawn"
		 */
		mrSerial.setName(ROUTE_RESPAWN);
		mrSerial.setParallel(false);
		
		
		ManualRunTaskDef endDef = new ManualRunTaskDef(pd,"EndTask");
		endDef.setSynchronised(true);
		MockRouting mrEnd = splitDef.addRoutingOut(endDef);
		/*
		 * finally the END task - 
		 * when the splitter task instance conditionaction is
		 * set to "end" the respawn of the splitter task will stop
		 */
		mrEnd.setName(ROUTE_END);
		mrEnd.setParallel(false);
		
		/*
		 * now run the workflow definition
		 */
	
		MockStateFactory msf = new MockStateFactory();
		MockEngine e = new MockEngine(msf);
		MockProcessInstance pi = (MockProcessInstance) e.createProcess(pd);
		
		e.startProcess(pi);
		
		/*
		 * check it's started as we expect 
		 * PI has 1 task
		 * 1xstartDef STATE_DELETED
		 * 1xsplitDef STATE_READY
		 */ 
		assertEquals(1,pi.getTaskInstances().size());
		assertEquals(1,msf.countInstances(startDef));
		assertEquals(1,pi.countInstances(splitDef,ITaskInstance.STATE_READY));
		
		// set the conditionaction to "respawn" and transition
		MockTaskInstance ti = pi.findTask(splitDef,ITaskInstance.STATE_READY);
		ti.setConditionAction(ROUTE_RESPAWN);
		
		e.transitionTask(ti);
		
		/*
		 * check the results of the transition
		 * we should have:
		 * 1xserialDef READY
		 * 1xsplitDef READY
		 */
		
		assertEquals(1,pi.countInstances(serialDef,ITaskInstance.STATE_READY));
		assertEquals(1,pi.countInstances(splitDef,ITaskInstance.STATE_READY));
		assertEquals(2,pi.getTaskInstances().size());
		
		// do the same again
		
		ti = pi.findTask(splitDef,ITaskInstance.STATE_READY);
		ti.setConditionAction(ROUTE_RESPAWN);
		
		e.transitionTask(ti);
		

		/*
		 * check the results of the transition
		 * we should have:
		 * 2xserialDef READY
		 * 1xsplitDef READY
		 */
		
		assertEquals(2,pi.countInstances(serialDef,ITaskInstance.STATE_READY));
		assertEquals(1,pi.countInstances(splitDef,ITaskInstance.STATE_READY));
		assertEquals(3,pi.getTaskInstances().size());
		
		/*
		 * audit trail should contain
		 * 2xsplitDef DELETED
		 * 1xstartDef DELETED
		 */
		assertEquals(2,msf.countInstances(splitDef,MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(startDef,MockTaskInstance.STATE_DELETED));
		
		
		/*
		 * now transition off to the END
		 */
		

		ti = pi.findTask(splitDef,ITaskInstance.STATE_READY);
		ti.setConditionAction(ROUTE_END);
		
		e.transitionTask(ti);
		
		/*
		 * check the results of the transition
		 * we should have:
		 * 2xserialDef READY
		 * 1xendDef READY
		 */
		
		assertEquals(2,pi.countInstances(serialDef,ITaskInstance.STATE_READY));
		assertEquals(1,pi.countInstances(endDef,ITaskInstance.STATE_READY));
		assertEquals(3,pi.getTaskInstances().size());
		
		/* 
		 * transition the endDef task
		 */
		ti = pi.findTask(endDef,ITaskInstance.STATE_READY);
		e.transitionTask(ti);
		
		/*
		 * check the results of the transition
		 * we should have:
		 * 2xserialDef READY
		 * PI = running
		 */
		
		assertEquals(2,pi.countInstances(serialDef,ITaskInstance.STATE_READY));
		assertEquals(2,pi.getTaskInstances().size());
		assertEquals(IProcessInstance.STATE_RUNNING,pi.getState());
		
		// get rid of the final 2 tasks
		
		ti = pi.findTask(serialDef,ITaskInstance.STATE_READY);
		e.transitionTask(ti);
		ti = pi.findTask(serialDef,ITaskInstance.STATE_READY);
		e.transitionTask(ti);
		
		/*
		 * check process completed
		 */
		assertEquals(IProcessInstance.STATE_COMPLETE,pi.getState());
	}
	
	
}
