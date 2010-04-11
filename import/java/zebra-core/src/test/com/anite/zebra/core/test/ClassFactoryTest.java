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
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.processdef.ClassFactoryProcess;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.factory.CachedClassFactory;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.processconstruct.MockProcessConstruct;
import com.anite.zebra.core.processdestruct.MockProcessDestruct;
import com.anite.zebra.core.routingcondition.MockRoutingCondition;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.taskaction.MockTaskAction;
import com.anite.zebra.core.taskconstruct.MockTaskConstruct;

/**
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class ClassFactoryTest extends TestCase {
	//private static Log log = LogFactory.getLog(ClassFactoryTest.class);

	public void testClassFactory() throws Exception {
		
		ClassFactoryProcess pd = new ClassFactoryProcess("testClassFactoryFailBehaviour");
		
		CachedClassFactory ccf = new CachedClassFactory();
		MockStateFactory msf = new MockStateFactory();
		IEngine e = new Engine(msf,ccf);
		
		MockProcessInstance pi = (MockProcessInstance) e.createProcess(pd);
		e.startProcess(pi);
		assertEquals(0,pi.getTaskInstances().size());
		
		assertEquals(1,((MockProcessConstruct) ccf.getProcessConstruct(MockProcessConstruct.class.getName())).getRunCount());
		assertEquals(1,((MockProcessDestruct) ccf.getProcessDestruct(MockProcessDestruct.class.getName())).getRunCount());

		assertEquals(1,((MockTaskConstruct) ccf.getTaskConstruct(MockTaskConstruct.class.getName())).getRunCount());
		assertEquals(1,((MockTaskAction) ccf.getTaskAction(MockTaskAction.class.getName())).getRunCount());
		// not implemented - may need to remove
		//assertEquals(0,((MockTaskDestruct) ccf.getTaskDestruct(MockTaskDestruct.class.getName())).getRunCount());
	
		assertEquals(1,((MockRoutingCondition) ccf.getConditionAction(MockRoutingCondition.class.getName())).getRunCount());
		
	}
	public void testClassFactoryFailBehaviour() throws Exception {
		ClassFactoryProcess pd = new ClassFactoryProcess("testClassFactoryFailBehaviour");
		CachedClassFactory ccf = new CachedClassFactory();
		MockStateFactory msf = new MockStateFactory();
		IEngine eng = new Engine(msf,ccf);
		
		// start and run once to prove it works
		MockProcessInstance pi = (MockProcessInstance) eng.createProcess(pd);
		eng.startProcess(pi);
		// make routing invalid and try again
		pd = new ClassFactoryProcess("testFailRouting");
		pd.testRouting.setConditionClass(">>fail<<");
		runFailTest(eng,pd);		
		
		// make taskconstruct invalid and try again
		pd = new ClassFactoryProcess("testFailTaskConstruct");
		pd.testTask.setClassConstruct(">>fail<<");
		runFailTest(eng,pd);		
		
		// make taskaction invalid and try again
		pd = new ClassFactoryProcess("testFailTaskAction");
		pd.testTask.setClassName(">>fail<<");
		runFailTest(eng,pd);		
		
		// make processConstruct invalid and try again
		pd = new ClassFactoryProcess("testFailProcessConstruct");
		pd.setClassConstruct(">>fail<<");
		runFailTest(eng,pd);		

		// make processDestruct invalid and try again
		pd = new ClassFactoryProcess("testFailProcessDestruct");
		pd.setClassDestruct(">>fail<<");
		runFailTest(eng,pd);		

	}
	private void runFailTest(IEngine eng, IProcessDefinition pd) throws CreateProcessException {
		MockProcessInstance pi = (MockProcessInstance) eng.createProcess(pd);
		Exception caught=null;
		try {
			eng.startProcess(pi);
		} catch (StartProcessException e) {
			caught = e;
		}
		assertNotNull(caught);

	}
}
