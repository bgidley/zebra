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

import java.util.HashMap;
import java.util.Map;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;


/**
 * @author Eric Pugh
 */
public class MemoryStateFactory implements IStateFactory {
	/**
	 * @return Returns the allProcessInstances.
	 */
	public static Map getAllProcessInstances() {
		return allProcessInstances;
	}
	/**
	 * @return Returns the allTaskInstances.
	 */
	public static Map getAllTaskInstances() {
		return allTaskInstances;
	}
	private static Map processInstances = new HashMap();
	private static Map taskInstances = new HashMap();
	private static Map allProcessInstances = new HashMap();
	private static Map allTaskInstances = new HashMap();
	public ITransaction beginTransaction() throws StateFailureException {
		return new MemoryTransaction();
	}

	public IFOE createFOE(IProcessInstance processInstance)
			throws CreateObjectException {
		return new MemoryFOE(processInstance);
	}

	public IProcessInstance createProcessInstance(IProcessDefinition processDef)
			throws CreateObjectException {

		MemoryProcessInstance processInstance = new MemoryProcessInstance();
		processInstance.setProcessDef(processDef);
		return processInstance;
	}

	public ITaskInstance createTaskInstance(ITaskDefinition taskDef,
			IProcessInstance processInstance, IFOE foe)
			throws CreateObjectException {
		MemoryTaskInstance taskInstance = new MemoryTaskInstance();
		taskInstance.setFoe(foe);
		taskInstance.setProcessInstance(processInstance);
		taskInstance.setTaskDef(taskDef);
		
		processInstance.getTaskInstances().add(taskInstance);
		return taskInstance;
	}

	public void deleteObject(IStateObject so) throws StateFailureException {
		if (so instanceof IProcessInstance) {
			MemoryProcessInstance processInstance = (MemoryProcessInstance) so;			
			processInstances.remove(processInstance.getProcessInstanceId());
		}
		else if (so instanceof ITaskInstance) {
			MemoryTaskInstance taskInstance = (MemoryTaskInstance) so;
			taskInstance.getProcessInstance().getTaskInstances().remove(taskInstance);
			taskInstances.remove(taskInstance.getTaskInstanceId());
		}

	}
	
	public void saveObject(IStateObject so) throws StateFailureException {
		if (so instanceof IProcessInstance) {
			MemoryProcessInstance processInstance = (MemoryProcessInstance) so;
			processInstances.put(processInstance.getProcessInstanceId(),
					processInstance);
			allProcessInstances.put(processInstance.getProcessInstanceId(),
					processInstance);

		}
		else if (so instanceof ITaskInstance) {
			MemoryTaskInstance taskInstance = (MemoryTaskInstance) so;
			taskInstances.put(taskInstance.getTaskInstanceId(),
					taskInstance);
			allTaskInstances.put(taskInstance.getTaskInstanceId(),
					taskInstance);			
		}		

	}
	/**
	 * @return Returns the processInstances.
	 */
	public static Map getProcessInstances() {
		return processInstances;
	}
	/**
	 * @return Returns the taskInstances.
	 */
	public static Map getTaskInstances() {
		return taskInstances;
	}
    
    /* (non-Javadoc)
     * @see com.anite.zebra.core.state.api.IProcessInstance#AcquireLock()
     */
    public void acquireLock(IProcessInstance processInstance) throws LockException {

    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.state.api.IProcessInstance#ReleaseLock()
     */
    public void releaseLock(IProcessInstance processInstance) throws LockException {

    }
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#acquireLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
	 */
	public void acquireLock(IProcessInstance arg0, IEngine arg1) throws LockException {
		// TODO Auto-generated method stub
		
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#releaseLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
	 */
	public void releaseLock(IProcessInstance arg0, IEngine arg1) throws LockException {
		// TODO Auto-generated method stub
		
	}    
}