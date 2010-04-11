package com.anite.zebra.core.test;

import java.util.Set;

import junit.framework.TestCase;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.JoinTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.SplitTaskDef;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

public class SplitJoinTest extends TestCase {
	private static Log log = LogFactory.getLog(SplitJoinTest.class);
	
    
	public void testSimpleSplitJoin() throws Exception {
		MockProcessDef pd = new MockProcessDef("testSimpleSplitJoin"); 
		ManualRunTaskDef tdStart = new ManualRunTaskDef(pd,"Start");
		pd.setFirstTask(tdStart);
		SplitTaskDef tdSplit = new SplitTaskDef(pd,"Split");
		tdSplit.setAuto(true);
		tdStart.addRoutingOut(tdSplit);
		JoinTaskDef tdJoin = new JoinTaskDef(pd,"Join");
		tdJoin.setAuto(true);
		AutoRunTaskDef tdParallel1 = new AutoRunTaskDef (pd,"Parallel-1");
		tdSplit.addRoutingOut(tdParallel1);
		tdParallel1.addRoutingOut(tdJoin);
		AutoRunTaskDef tdParallel2 = new AutoRunTaskDef (pd,"Parallel-2");
		tdSplit.addRoutingOut(tdParallel2);		
		tdParallel2.addRoutingOut(tdJoin);
		
		AutoRunTaskDef tdEndTask = new AutoRunTaskDef(pd,"End Task");
		tdJoin.addRoutingOut(tdEndTask);
		
		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		IProcessInstance processInstance = engine.createProcess(pd);

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
		
		ITaskInstance ti = (ITaskInstance) taskInstances.iterator().next();
		assertEquals(tdStart, ti.getTaskDefinition());
		log.info("Transitioning Task " + ti.getTaskInstanceId());
		engine.transitionTask(ti);
		// test to see if we have the expected number of tasks - NONE
		taskInstances = processInstance.getTaskInstances();
		assertEquals(0, taskInstances.size());
		/* test to see if the audit log is the expected size -
		 * 1 process
		 * 1 start task
		 * 1 split task
		 * 2 parallel tasks
		 * 1 join task
		 *  = 6 objects
		 * + 4 FOE
		 * 1 x start to split
		 * 1 x parallel 1
		 * 1 x parallel 2
		 * 1 x join onwards
		 * 1 x end task
		 *  = 11
		 */ 
		
		assertEquals(11, msf.getAuditTrail().size());
		assertEquals(4,msf.countFOE(processInstance));
		// test to see all are marked as "completed" / "deleted" as appropriate
		assertEquals(1,msf.countInstances(pd));
		assertEquals(1,msf.countInstances(tdStart));
		assertEquals(1,msf.countInstances(tdSplit));
		assertEquals(1,msf.countInstances(tdParallel1));
		assertEquals(1,msf.countInstances(tdParallel2));
		assertEquals(1,msf.countInstances(tdJoin));
		assertEquals(1,msf.countInstances(tdEndTask, MockTaskInstance.STATE_DELETED));
		
		tdEndTask.setAuto(false);
		
		// rerun the test
		msf = new MockStateFactory();
		engine = new Engine(msf);
		processInstance = engine.createProcess(pd);
		engine.startProcess(processInstance);
		taskInstances = processInstance.getTaskInstances();
		ti = (ITaskInstance) taskInstances.iterator().next();
		assertEquals(tdStart, ti.getTaskDefinition());
		log.info("Transitioning Task " + ti.getTaskInstanceId());
		engine.transitionTask(ti);
		// test to see if we have the expected number of tasks - NONE
		taskInstances = processInstance.getTaskInstances();
		// just the "end task" should remain
		assertEquals(1, taskInstances.size());
		ti = (ITaskInstance) taskInstances.iterator().next();
		engine.transitionTask(ti);
		/* test to see if the audit log is the expected size -
		 * 1 process
		 * 1 start task
		 * 1 split task
		 * 2 parallel tasks
		 * 1 join task
		 *  = 6 objects
		 * + 4 FOE
		 * 1 x start to split
		 * 1 x parallel 1
		 * 1 x parallel 2
		 * 1 x join onwards
		 * 1 x end task 
		 *  = 11
		 */ 
		
		assertEquals(11, msf.getAuditTrail().size());
		assertEquals(4,msf.countFOE(processInstance));
		// test to see all are marked as "completed" / "deleted" as appropriate
		assertEquals(1,msf.countInstances(pd));
		assertEquals(1,msf.countInstances(tdStart));
		assertEquals(1,msf.countInstances(tdSplit));
		assertEquals(1,msf.countInstances(tdParallel1));
		assertEquals(1,msf.countInstances(tdParallel2));
		assertEquals(1,msf.countInstances(tdJoin));
		assertEquals(1,msf.countInstances(tdEndTask, MockTaskInstance.STATE_DELETED));
	}
}
