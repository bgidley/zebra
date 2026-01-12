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
package com.anite.zebra.ext.state.memory;

import junit.framework.TestCase;

import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;


/**
 * @author Eric Pugh
 * 
 * TODO To change the template for this generated type comment go to Window -
 * Preferences - Java - Code Style - Code Templates
 */
public class MemoryStateFactoryTest extends TestCase {
	
	public void testCreatingTransaction() throws StateFailureException{
		MemoryStateFactory msf = new MemoryStateFactory();
		ITransaction transaction = msf.beginTransaction();
		assertNotNull(transaction);
		transaction.commit();
		
	}
	
	public void testLoadSaveObjects() throws Exception{
		MemoryStateFactory msf = new MemoryStateFactory();
		IProcessInstance processInstance = msf.createProcessInstance(new ProcessDefinition());
		msf.saveObject(processInstance);
		assertTrue(MemoryStateFactory.getProcessInstances().containsValue(processInstance));

		MemoryFOE memoryFOE = new MemoryFOE(processInstance);
		ITaskInstance taskInstance = msf.createTaskInstance(new TaskDefinition(),processInstance, memoryFOE);
		
		msf.saveObject(processInstance);
		msf.saveObject(taskInstance);
		assertTrue(MemoryStateFactory.getProcessInstances().containsValue(processInstance));
		assertTrue(MemoryStateFactory.getTaskInstances().containsValue(taskInstance));
		
		
		msf.deleteObject(processInstance);
		msf.deleteObject(taskInstance);
		
		assertFalse(processInstance.getTaskInstances().contains(taskInstance));		
		
		assertTrue(MemoryStateFactory.getAllProcessInstances().containsValue(processInstance));
		assertTrue(MemoryStateFactory.getAllTaskInstances().containsValue(taskInstance));
		
	}
	
	public void testCreatingFOE() throws Exception{
		MemoryStateFactory msf = new MemoryStateFactory();
		IFOE foe = msf.createFOE(new MemoryProcessInstance());
		assertNotNull(foe);
		
	}
	
	public void testCreatingTaskInstance() throws Exception{
		MemoryStateFactory msf = new MemoryStateFactory();
		IProcessInstance processInstance = new MemoryProcessInstance();
		MemoryFOE memoryFOE = new MemoryFOE(processInstance);
		ITaskInstance taskInstance = msf.createTaskInstance(new TaskDefinition(),processInstance, memoryFOE);
		assertTrue(taskInstance.getTaskInstanceId().longValue()>0);
	}

}