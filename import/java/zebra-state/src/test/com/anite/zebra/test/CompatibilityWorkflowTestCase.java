package com.anite.zebra.test;

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

import java.util.HashSet;
import java.util.Set;

import junit.framework.TestCase;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * Tests to verify that multiple implementations of the StateFactory all
 * function the same.
 * 
 * @author Eric.Pugh
 */
public abstract class CompatibilityWorkflowTestCase extends TestCase {
	public abstract IStateFactory createStateFactory();
	public void testSimpleWorkflow() throws Exception {
		
		

		/*lf.loadProcessDef(new File("src/test/test-resources/simple.acgwfd.xml").getAbsoluteFile(),
				"com.anite.zebra.ext.definitions.impl.ProcessDefinition",
				"com.anite.zebra.ext.definitions.impl.TaskDefinition");
*/
		
	
        ProcessDefinition processDef = new ProcessDefinition();
        TaskDefinition taskDef1 = new TaskDefinition();
        taskDef1.setAuto(Boolean.TRUE);
        taskDef1.setId(new Long(1));
        taskDef1.setName("Activity");
        taskDef1.setSynchronise(false);
        //taskDef1.setClassName("com.anite.zebra.test.MockTaskAction");
        Set taskDefs = new HashSet();
        
        TaskDefinition taskDef2 = new TaskDefinition();
        taskDef2.setAuto(Boolean.FALSE);
        taskDef2.setId(new Long(2));
       // taskDef2.setClassName("com.anite.zebra.test.MockTaskAction");
        taskDef2.setSynchronise(false);
        
        taskDefs.add(taskDef1);
        taskDefs.add(taskDef2);
              
        
        processDef.setFirstTask(taskDef1);
        
        processDef.setTaskDefinitions(taskDefs);
        
        Set routingDefs = new HashSet();
        RoutingDefinition routingDef1 = new RoutingDefinition();
        routingDef1.setOriginatingTaskDefinition(taskDef1);
        routingDef1.setDestinationTaskDefinition(taskDef2);
        routingDef1.setId(new Long(1));
        routingDef1.setName("");
        routingDef1.setConditionClass("com.anite.zebra.test.AlwaysTrueRoutingCondition");
        routingDefs.add(routingDef1);
        
        processDef.setRoutingDefinitions(routingDefs);
        taskDef1.getRoutingOut().add(routingDef1);
        taskDef2.getRoutingIn().add(routingDef1);
        
		
		
		
		IEngine engine = new Engine(createStateFactory());
		IProcessInstance processInstance = engine.createProcess(processDef);
		assertEquals(processDef,processInstance.getProcessDef());
		assertTrue(processInstance.getProcessInstanceId().longValue()>0);
		assertEquals(IProcessInstance.STATE_CREATED,processInstance.getState());
		Set taskInstances = processInstance.getTaskInstances();
		assertEquals(0,taskInstances.size());
		engine.startProcess(processInstance);
		assertEquals(1,processInstance.getTaskInstances().size());
		assertEquals(IProcessInstance.STATE_RUNNING,processInstance.getState());
		
		postTestSimpleWorkflow();
		
	}
	
	public void postTestSimpleWorkflow() throws Exception{
		
	}
	
}