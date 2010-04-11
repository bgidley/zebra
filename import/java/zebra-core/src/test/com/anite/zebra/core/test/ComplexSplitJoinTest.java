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
package com.anite.zebra.core.test;

import java.util.Set;

import junit.framework.TestCase;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.processdef.ComplexProcessDef;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 *
 * Tests whether a complex split / join operation works correctly
 * 
 * @author Matthew Norris
 * Created on 19-Aug-2005
 *
 */
public class ComplexSplitJoinTest extends TestCase {

	private static Log log = LogFactory.getLog(ComplexSplitJoinTest.class);
	
	/*
	 * the following fields are needed to allow the various tests
	 * to check the FOE of tasks that have been run#
	 * 
	 * they are populated from doPart1
	 */
	private MockTaskInstance tiStart;
	private MockTaskInstance tiSplit;
	private MockTaskInstance tiParallel_1;
	private MockTaskInstance tiParallel_2;
	private MockTaskInstance tiJoin;
	
	public void testAlternateEnding() throws Exception {
		
		ComplexProcessDef pd = new ComplexProcessDef("complexTest1");
		
		
		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		MockProcessInstance processInstance = (MockProcessInstance) engine.createProcess(pd);

		// first transition test - runs the workflow up to the point where it hits the JOIN
		doPart1(pd, engine, processInstance);
		
		/*
		 * now transition the workflow toward the alternate ending
		 */
		tiParallel_2.setConditionAction(ComplexProcessDef.GOTO + pd.tdAlternateEnding.getName());
		engine.transitionTask(tiParallel_2);
		
		engine.transitionTask(tiJoin);
		
		/*
		 * check to see if we have the expected number of object in the audit trail
		 * 1 x process
		 * 1 x tdStart (complete)
		 * 1 x tdSplit (complete)
		 * 1 x tdJoin (complete)
		 * 1 x tdParallel-1 (complete)
		 * 1 x tdParallel-2 (complete)
		 * 1 x tdAlternateEnding (ready)
		 * 1 x tdEnd (ready)
		 * 4 x FOE
		 *  - 1 x up to Split
		 *  - 1 x tdParallel-1
		 *  - 1 x tdParallel-2, tdAlernateEnding
		 *  - 1 x tdJoin,tdEnd
		 */
		assertEquals(1,msf.getFOEs(processInstance,pd.tdStart).size());
		assertEquals(1,msf.getFOEs(processInstance,pd.tdParallel_1).size());
		assertEquals(1,msf.getFOEs(processInstance,pd.tdParallel_2).size());
		assertEquals(1,msf.getFOEs(processInstance,pd.tdAlternateEnding).size());
		assertEquals(1,msf.getFOEs(processInstance,pd.tdJoin).size());
		assertEquals(1,msf.getFOEs(processInstance,pd.tdEnd).size());
		assertEquals(4,msf.countFOE(processInstance));
		
		assertEquals(1,msf.countInstances(pd));
		assertEquals(1,msf.countInstances(pd.tdStart, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdSplit, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdJoin, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdParallel_1, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdParallel_2, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdEnd, MockTaskInstance.STATE_READY));
		assertEquals(1,msf.countInstances(pd.tdAlternateEnding, MockTaskInstance.STATE_READY));
	}
	
	public void testLoopingJoin() throws Exception {
		
		
		ComplexProcessDef pd = new ComplexProcessDef("complexTest1");
		
		
		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		MockProcessInstance processInstance = (MockProcessInstance) engine.createProcess(pd);

		// first transition test - runs the workflow up to the point where it hits the JOIN
		doPart1(pd, engine, processInstance);		
		
		tiParallel_2.setConditionAction(ComplexProcessDef.GOTO + pd.tdSplit.getName());
		engine.transitionTask(tiParallel_2);
		
		ITaskInstance tiSplit_b = processInstance.findTask(pd.tdSplit,MockTaskInstance.STATE_READY);
		assertNotNull("Failed to find the task to run",tiSplit_b);
		engine.transitionTask(tiSplit_b);

		ITaskInstance tiParallel_1b = processInstance.findTask(pd.tdParallel_1,MockTaskInstance.STATE_READY);
		assertNotNull("Failed to find the task to run",tiParallel_1b);
		engine.transitionTask(tiParallel_1b);
		/*
		 * check to see if we have the expected number of object in the audit trail
		 * 1 x process
		 * 1 x tdStart (complete)
		 * 2 x tdSplit (complete)
		 * 1 x tdJoin (awaiting sync)
		 * 2 x tdParallel-1 (complete)
		 * 2 x tdParallel-2 (1 x complete, 1 x ready)
		 * 
		 * 5 x FOE
		 *  - 1 x start
		 *  - 1 x split
		 *  - 1 x split
		 */
		
		assertEquals(1,msf.countInstances(pd));
		assertEquals(1,msf.countInstances(pd.tdStart, MockTaskInstance.STATE_DELETED));
		assertEquals(2,msf.countInstances(pd.tdSplit, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdJoin, MockTaskInstance.STATE_AWAITINGSYNC));
		assertEquals(2,msf.countInstances(pd.tdParallel_1, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdParallel_2, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdParallel_2, MockTaskInstance.STATE_READY));
		
		MockTaskInstance tiParallel_2b = processInstance.findTask(pd.tdParallel_2,ITaskInstance.STATE_READY);
		
		assertNotSame(tiParallel_1b.getFOE(),tiSplit.getFOE());
		
		assertNotSame(tiParallel_2b.getFOE(),tiSplit.getFOE());
		assertNotSame(tiParallel_2b.getFOE(),tiSplit_b.getFOE());
		
		assertNotSame(tiParallel_1.getFOE(),tiParallel_2b.getFOE());
		assertNotSame(tiParallel_2.getFOE(),tiParallel_2b.getFOE());
		
		assertNotSame(tiJoin.getFOE(),tiSplit_b.getFOE());
		
		assertNotSame(tiJoin.getFOE(),tiParallel_1b.getFOE());
		assertNotSame(tiJoin.getFOE(),tiParallel_2b.getFOE());
		
		
		/*
		 * check that we've got what we expect in the process instance
		 * 1 x tdJoin
		 * 1 x tdParallel2
		 */
		assertEquals(2,processInstance.getTaskInstances().size());
		assertEquals(1,processInstance.countInstances(pd.tdParallel_2,MockTaskInstance.STATE_READY));
		assertEquals(1,processInstance.countInstances(pd.tdJoin,MockTaskInstance.STATE_AWAITINGSYNC));
		
		/*
		 * now transition again, but go to the JOIN
		 */
		tiParallel_2b.setConditionAction(ComplexProcessDef.GOTO + pd.tdJoin.getName());
		engine.transitionTask(tiParallel_2b);
	
		engine.transitionTask(tiJoin);
		
		/*
		 * check that we've got what we expect in the processinstance
		 * 1 x tdEnd
		 */
		assertEquals(1,processInstance.getTaskInstances().size());
		assertEquals(1,processInstance.countInstances(pd.tdEnd,MockTaskInstance.STATE_READY));
		
		/*
		 * check that we've still only got one Join task in the audit trail
		 */
		assertEquals(1,msf.countInstances(pd.tdJoin));
		
		/*
		 * now transition again to complete
		 */
		MockTaskInstance tiEnd = processInstance.findTask(pd.tdEnd,MockTaskInstance.STATE_READY);
		assertNotNull("Failed to find the task to run",tiEnd);
		engine.transitionTask(tiEnd);
		
		/*
		 * check there are no outstanding tasks & the process is complete 
		 */
		assertEquals(0,processInstance.getTaskInstances().size());
		assertTrue(processInstance.getState()==IProcessInstance.STATE_COMPLETE);
		
		/*
		 * check to see if we have the expected number of object in the audit trail
		 * 1 x process
		 * 1 x tdStart (complete)
		 * 2 x tdSplit (complete)
		 * 1 x tdJoin (complete)
		 * 2 x tdParallel-1 (complete)
		 * 2 x tdParallel-2 (complete)
		 * 1 x tdEnd (complete)
		 * 0 x tdAlternateEnding
		 */
		assertEquals(1,msf.countInstances(pd));
		assertEquals(1,msf.countInstances(pd.tdStart, MockTaskInstance.STATE_DELETED));
		assertEquals(2,msf.countInstances(pd.tdSplit, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdJoin, MockTaskInstance.STATE_DELETED));
		assertEquals(2,msf.countInstances(pd.tdParallel_1, MockTaskInstance.STATE_DELETED));
		assertEquals(2,msf.countInstances(pd.tdParallel_2, MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(pd.tdEnd, MockTaskInstance.STATE_DELETED));
		assertEquals(0,msf.countInstances(pd.tdAlternateEnding));

		assertSame(tiJoin.getFOE(),tiEnd.getFOE());
	}

	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @param pd
	 * @param engine
	 * @param processInstance
	 * @throws DefinitionNotFoundException
	 * @throws StartProcessException
	 * @throws TransitionException
	 */
	private void doPart1(ComplexProcessDef pd, IEngine engine, MockProcessInstance processInstance) throws DefinitionNotFoundException, StartProcessException, TransitionException {
		// tests to see if process is created properly 
		assertEquals(pd, processInstance.getProcessDef());
		assertTrue(processInstance.getProcessInstanceId().longValue() > 0);
		assertEquals(IProcessInstance.STATE_CREATED, processInstance.getState());

		// test to see if we have the expected number of tasks - NONE
		Set taskInstances = processInstance.getTaskInstances();
		assertEquals(0, taskInstances.size());
		log.info("Starting Process");
		engine.startProcess(processInstance);
		taskInstances = processInstance.getTaskInstances();
		// test to see if we have the expected number of tasks - ONE
		assertEquals(1, taskInstances.size());
		
		tiStart = (MockTaskInstance) taskInstances.iterator().next();
		assertEquals(pd.tdStart, tiStart.getTaskDefinition());
		engine.transitionTask(tiStart);
		
		tiSplit = (MockTaskInstance) taskInstances.iterator().next();
		assertEquals(pd.tdSplit, tiSplit.getTaskDefinition());

		// check FOE's match
		assertEquals(tiStart.getFOE(),tiSplit.getFOE());
		
		// transition
		engine.transitionTask(tiSplit);
		
		
		/* ensure the tasks are the ones we expect
		 * 1 x tdParallel1
		 * 1 x tdParallel2
		 */
		assertEquals(2,processInstance.getTaskInstances().size());
		assertEquals(1,processInstance.countInstances(pd.tdParallel_1,MockTaskInstance.STATE_READY));
		assertEquals(1,processInstance.countInstances(pd.tdParallel_2,MockTaskInstance.STATE_READY));
		
		tiParallel_1 = (MockTaskInstance) processInstance.findTask(pd.tdParallel_1,MockTaskInstance.STATE_READY);
		// check FOE is new
		assertNotSame(tiSplit.getFOE(),tiParallel_1.getFOE());
		
		// transition
		engine.transitionTask(tiParallel_1);

		/* ensure the tasks are the ones we expect
		 * 1 x tdJoin
		 * 1 x tdParallel2
		 */
		assertEquals(2,processInstance.getTaskInstances().size());
		assertEquals(1,processInstance.countInstances(pd.tdJoin,MockTaskInstance.STATE_AWAITINGSYNC));
		assertEquals(1,processInstance.countInstances(pd.tdParallel_2,MockTaskInstance.STATE_READY));
		
		// check FOE's
		
		tiParallel_2 = processInstance.findTask(pd.tdParallel_2,MockTaskInstance.STATE_READY);
		assertNotSame(tiParallel_2.getFOE(),tiParallel_1.getFOE());

		tiJoin = processInstance.findTask(pd.tdJoin,MockTaskInstance.STATE_AWAITINGSYNC);
		assertNotSame(tiJoin.getFOE(),tiSplit.getFOE());
		assertNotSame(tiJoin.getFOE(),tiParallel_1.getFOE());
		assertNotSame(tiParallel_2.getFOE(),tiJoin.getFOE());
		
	}
}
