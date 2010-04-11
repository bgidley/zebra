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

import junit.framework.TestCase;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.taskdefs.JoinTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.definitions.taskdefs.SplitTaskDef;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;

/**
 * @author Matthew.Norris
 * Created on Aug 19, 2005
 */
public class RecursiveSplitTest extends TestCase {
	
	public void testDirectRecursiveSplit() throws Exception {
		MockProcessDef pd = new MockProcessDef("testDirectRecursiveSplit");
		MockTaskDef tdSplit = new SplitTaskDef(pd,"Split");
		pd.setFirstTask(tdSplit);
		
		tdSplit.addRoutingOut(tdSplit).setName("Goto Split");
		
		MockTaskDef tdJoin = new JoinTaskDef(pd,"Join");
		tdJoin.setAuto(true);
		tdSplit.addRoutingOut(tdJoin).setName("Goto Join");
		
		
		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		
		MockProcessInstance pi = (MockProcessInstance) engine.createProcess(pd);
		engine.startProcess(pi);
				
		MockTaskInstance ti = pi.findTask(tdSplit,MockTaskInstance.STATE_READY);
		
		ti.setConditionAction("Goto Split");
		
		engine.transitionTask(ti);
		
		ti = pi.findTask(tdSplit,MockTaskInstance.STATE_READY);
		
		ti.setConditionAction("Goto Join");
		
		engine.transitionTask(ti);
		
		/*
		 * check expected results
		 */
		assertEquals(0,pi.getTaskInstances().size());
		assertEquals(2,msf.countInstances(tdSplit,MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(tdJoin,MockTaskInstance.STATE_DELETED));
		
	}
	public void testDirectRecursiveSplitWithLimboTask() throws Exception {
		MockProcessDef pd = new MockProcessDef("testDirectRecursiveSplitWithLimboTask");
		MockTaskDef tdSplit = new SplitTaskDef(pd,"Split");
		pd.setFirstTask(tdSplit);
		tdSplit.setAuto(false);
		
		tdSplit.addRoutingOut(tdSplit).setName("Goto Split");
		
		MockTaskDef tdLimbo = new ManualRunTaskDef(pd,"Limbo");
		MockRouting mrLimbo =  tdSplit.addRoutingOut(tdLimbo);
		mrLimbo.setName("Always going to Limbo");
		mrLimbo.setConditionClass(null);
		mrLimbo.setParallel(false);
		
		MockTaskDef tdJoin = new JoinTaskDef(pd,"Join");
		tdJoin.setAuto(true);
		tdSplit.addRoutingOut(tdJoin).setName("Goto Join");
		
		
		MockStateFactory msf = new MockStateFactory();
		IEngine engine = new Engine(msf);
		
		MockProcessInstance pi = (MockProcessInstance) engine.createProcess(pd);
		engine.startProcess(pi);
		
		MockTaskInstance ti = pi.findTask(tdSplit,MockTaskInstance.STATE_READY);
		
		ti.setConditionAction("Goto Split");
		
		engine.transitionTask(ti);
		
		ti = pi.findTask(tdSplit,MockTaskInstance.STATE_READY);
		
		ti.setConditionAction("Goto Join");
		
		engine.transitionTask(ti);
		
		/*
		 * check expected results
		 * 1xProcess (running)
		 * 2xSplit (completed)
		 * 1xJoin (completed)
		 * 2xLimbo (completed)
		 * 4x FOE
		 *  - 1 x to split
		 *  - 2 x split to limbo 
		 *  - 1 x join onwards
		 */
		assertEquals(10,msf.getAuditTrail().size());
		assertEquals(4,msf.getFOEs(pi).size());
		assertEquals(2,pi.getTaskInstances().size());
		assertEquals(2,msf.countInstances(tdSplit,MockTaskInstance.STATE_DELETED));
		assertEquals(1,msf.countInstances(tdJoin,MockTaskInstance.STATE_DELETED));
		assertEquals(2,msf.countInstances(tdLimbo,MockTaskInstance.STATE_READY));
		assertEquals(MockProcessInstance.STATE_RUNNING,pi.getState());
	}
}
