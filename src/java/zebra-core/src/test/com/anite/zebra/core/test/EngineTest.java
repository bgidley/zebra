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

import java.util.Set;

import junit.framework.TestCase;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.routingcondition.AlwaysFalseConditionAction;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Simple tests of the Engine
 * @author Matthew.Norris
 */
public class EngineTest extends TestCase {

	/**
	 * tests a simple workflow with automated steps
	 * @throws Exception
	 *
	 * @author Matthew.Norris
	 */
	public void testWorkflowWithAutoSteps() throws Exception {

		MockProcessDef processDef = new MockProcessDef("");

		AutoRunTaskDef taskDef = new AutoRunTaskDef(processDef, "");

		processDef.setFirstTask(taskDef);

		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		
		IProcessInstance processInstance = engine.createProcess(processDef);
		assertEquals(processDef, processInstance.getProcessDef());
		assertTrue(processInstance.getProcessInstanceId().longValue() > 0);
		assertEquals(IProcessInstance.STATE_CREATED, processInstance.getState());

		Set taskInstances = processInstance.getTaskInstances();
		assertEquals(0, taskInstances.size());
		engine.startProcess(processInstance);
		
		assertEquals(0, processInstance.getTaskInstances().size());
		assertEquals(IProcessInstance.STATE_COMPLETE, processInstance
				.getState());
		assertEquals(1,msf.countFOE(processInstance));
		assertEquals(3,msf.getAuditTrail().size());
		assertEquals(1,msf.countInstances(processDef));
		assertEquals(1,msf.countInstances(taskDef,MockTaskInstance.STATE_DELETED));
	}

	public void testWorkflowWithManualSteps() throws Exception {

		MockProcessDef processDef = new MockProcessDef("");
		
		ManualRunTaskDef taskDef = new ManualRunTaskDef(processDef,"");

		processDef.setFirstTask(taskDef);

		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		MockProcessInstance processInstance = (MockProcessInstance) engine.createProcess(processDef);
		assertEquals(processDef, processInstance.getProcessDef());
		assertTrue(processInstance.getProcessInstanceId().longValue() > 0);
		assertEquals(IProcessInstance.STATE_CREATED, processInstance.getState());
		
		Set taskInstances = processInstance.getTaskInstances();
		assertEquals(0, taskInstances.size());
		engine.startProcess(processInstance);
		
		assertEquals(1, processInstance.getTaskInstances().size());
		assertEquals(IProcessInstance.STATE_RUNNING, processInstance.getState());
		
		MockTaskInstance ti = processInstance.findTask(taskDef,ITaskInstance.STATE_READY);
		assertNotNull(ti);
		
		engine.transitionTask(ti);
		
		assertEquals(IProcessInstance.STATE_COMPLETE, processInstance.getState());
		assertEquals(0, processInstance.getTaskInstances().size());
		
		assertEquals(1,msf.countFOE(processInstance));
		assertEquals(3,msf.getAuditTrail().size());
		assertEquals(1,msf.countInstances(processDef));
		assertEquals(1,msf.countInstances(taskDef,MockTaskInstance.STATE_DELETED));
		
	}
	/**
	 * tests to see if an exception is thrown when there are routings on a workflow but none ran
	 */
	public void testWorkflowRoutingNotRun() throws Exception {
		MockProcessDef pd = new MockProcessDef("testWorkflowRoutingNotRun");
		MockTaskDef tdStart = new AutoRunTaskDef(pd,"Start");
		MockTaskDef tdEnd = new AutoRunTaskDef(pd,"End");
		MockRouting mr = tdStart.addRoutingOut(tdEnd);
		mr.setConditionClass(AlwaysFalseConditionAction.class.getName());
		pd.setFirstTask(tdStart);
		
		MockStateFactory msf = new MockStateFactory();
		IEngine eng = new Engine(msf);
		IProcessInstance pi = eng.createProcess(pd);
		Exception caught = null;
		try {
			eng.startProcess(pi);
		} catch (Exception e) {
			caught = e;
		}
		assertNotNull(caught);
		assertTrue((caught.getCause().getMessage().indexOf("Routing exists")>0) && (caught.getCause().getMessage().indexOf("but none ran")>0));
		
	}
}