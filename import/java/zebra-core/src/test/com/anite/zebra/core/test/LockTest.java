/*
 * Copyright 2005 Anite - Enforcement & Security
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

import java.util.HashSet;
import java.util.Set;

import junit.framework.TestCase;

import com.anite.zebra.core.MockEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.taskaction.WaitForKick;
import com.anite.zebra.core.taskconstruct.MockTaskConstruct;

/**
 * 
 * Tests that the clustering / locking mechanisms work correctly.
 * 
 * @author Matthew.Norris
 * Created on 22-Sep-2005
 */
public class LockTest extends TestCase {
	
	public void testLocking() throws Exception {
		CheckLocking c = new CheckLocking();
		Thread t = new Thread(c,"checkLocking");
		// allow 15 seconds for the test to run
		long timeout = System.currentTimeMillis() + 15000;
		t.start();
		
		while (t.isAlive()) {
			if (System.currentTimeMillis()>timeout) {
				t.interrupt();
				fail("Test took too long - killed the test thread");
			}
		}
		assertTrue(c.passed);
	}
	
	
	/**
	 * @param mcLeft
	 * @param mcRight
	 * @param t1
	 * @param t2
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	private void checkThreads(MockCluster mcLeft, MockCluster mcRight, Thread t1, Thread t2) {
		assertNull("Left thread suffered an Exception",mcLeft.e);
		assertNull("Right thread suffered an Exception",mcRight.e);
		if (mcLeft.e!=null || mcRight.e!=null) {
			t1.interrupt();
			t2.interrupt();
			fail();
		}
	}

	class CheckLocking implements Runnable {
		public boolean passed = false;
		/* (non-Javadoc)
		 * @see java.lang.Runnable#run()
		 */
		public void run() {
			try {
				runTheTest();
			} catch (Exception e) {
				fail();
			}
			passed=true;
			
		}

		private void runTheTest() throws CreateProcessException, StartProcessException, DefinitionNotFoundException, InterruptedException, TransitionException {
			Set auditTrail = new HashSet();

			MockStateFactory msf = new MockStateFactory();
			msf.setAuditTrail(auditTrail);
			MockEngine me = new MockEngine(msf);
			
			MockProcessDef processDef = new MockProcessDef("LockTest");

			AutoRunTaskDef startDef = new AutoRunTaskDef(processDef, "Start");

			processDef.setFirstTask(startDef);

			
			ManualRunTaskDef leftDef = new ManualRunTaskDef(processDef, "Left");
			leftDef.setClassName(WaitForKick.class.getName());
			MockRouting mr = startDef.addRoutingOut(leftDef);
			mr.setParallel(true);
			
			ManualRunTaskDef rightDef = new ManualRunTaskDef(processDef, "Right");
			rightDef.setClassName(WaitForKick.class.getName());
			mr = startDef.addRoutingOut(rightDef);
			mr.setParallel(true);
			
			ManualRunTaskDef joinDef = new ManualRunTaskDef(processDef, "Join");
			joinDef.setSynchronised(true);
			joinDef.setClassConstruct(MockTaskConstruct.class.getName());
			
			
			leftDef.addRoutingOut(joinDef);
			rightDef.addRoutingOut(joinDef);

//			AutoRunTaskDef endDef = new AutoRunTaskDef(processDef, "End");
//			joinDef.addRoutingOut(endDef);

			MockProcessInstance mpi = (MockProcessInstance) me.createProcess(processDef);
			me.startProcess(mpi);
			
			MockTaskInstance mtiLeft = mpi.findTask(leftDef,ITaskInstance.STATE_READY);
			MockTaskInstance mtiRight = mpi.findTask(rightDef,ITaskInstance.STATE_READY);
			
			MockCluster mcLeft = new MockCluster(auditTrail,mtiLeft);

			MockCluster mcRight = new MockCluster(auditTrail,mtiRight);
			
			Thread t1 = new Thread(mcLeft,"Left");
			
			Thread t2 = new Thread(mcRight,"Right");
			
			/*
			 * now have two threads with, each with own
			 * engine and state factory, but with each state
			 * factory linked to the same database (SET)
			 */

			t1.start();

			
			// ensure we dont continue until the task is running
			while (mtiLeft.getState()!=ITaskInstance.STATE_RUNNING) {
				Thread.sleep(250);
				checkThreads(mcLeft,mcRight,t1,t2);		
			}
			
			assertEquals("Process is locked",true,mpi.isLocked());
			
			// now start the second thread - it should be blocked by the first
			t2.start();
			
			assertEquals("Tasks are blocking",2,mpi.getTaskInstances().size());
			
			// tell the LEFT thread to wake up and complete
			mtiLeft.getPropertySet().put(WaitForKick.STOP_SLEEPING,"Wakey wakey");
			
			// wait for the LEFT thread to disappear from the running tasks
			while (mpi.getTaskInstances().contains(mtiLeft)) {
				Thread.sleep(100);
				checkThreads(mcLeft,mcRight,t1,t2);
			}

			// wait for the RIGHT task to start running 
			while (mtiRight.getState()!=ITaskInstance.STATE_RUNNING) {
				Thread.sleep(250);
				checkThreads(mcLeft,mcRight,t1,t2);
			}

			// tell the RIGHT thread to wake up and complete
			mtiRight.getPropertySet().put(WaitForKick.STOP_SLEEPING,"Wakey wakey");
			
			// wait for the RIGHT thread to hit "completed" status
			while (mpi.getTaskInstances().contains(mtiRight)) {
				Thread.sleep(100);
				checkThreads(mcLeft,mcRight,t1,t2);
			}

			/*
			 * as this is all happening asynchronously we have to wait 
			 * for the JOIN task to be created and be in the right state before
			 * continuing
			 */ 
			while (msf.countInstances(joinDef, MockTaskInstance.STATE_READY)==0) {
				Thread.sleep(100);
			}
			
			MockTaskInstance mtiJoin = mpi.findTask(joinDef,ITaskInstance.STATE_READY);
			
			// run it inline - no more threading woes!
			me.transitionTask(mtiJoin);
			
			// check we've no tasks left
			assertEquals(0,mpi.getTaskInstances().size());
			
			// check the audit trail contains 4 tasks
			assertEquals(1,msf.countInstances(startDef,MockTaskInstance.STATE_DELETED));
			assertEquals(1,msf.countInstances(leftDef,MockTaskInstance.STATE_DELETED));
			assertEquals(1,msf.countInstances(rightDef,MockTaskInstance.STATE_DELETED));
			assertEquals(1,msf.countInstances(joinDef,MockTaskInstance.STATE_DELETED));

		}
		
	}
	
	class MockCluster implements Runnable {

		private MockStateFactory msf;
		private MockEngine me;
		private MockTaskInstance mti;
		private Exception e = null;
		
		public MockCluster(Set commonAuditTrail, MockTaskInstance mti) {
			this.mti = mti;
			this.msf = new MockStateFactory();
			msf.setAuditTrail(commonAuditTrail);
			this.me = new MockEngine(msf); 
		}

		/* (non-Javadoc)
		 * @see java.lang.Runnable#run()
		 */
		public void run() {
			try {
				me.transitionTask(mti);
			} catch (TransitionException e) {
				this.e = e;
			}
		}
		
	}
}
