package com.anite.zebra.core.state;
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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * @author Matthew Norris
 */
public class MockProcessInstance implements IProcessInstance{
	
	
	/**
	 * constant used by the MOCKSTATEFACTORY
	 * to indicate this process instance has been DELETED
	 */
	public static final long STATE_DELETED = -100;
	/**
	 * used to generate a unique ID for each MockProcessInstance
	 * class created. See constructor.
	 */
	private static long counter=1;
	private Long processInstanceId = null;
	private IProcessDefinition processDef = null;
	
	/**
	 * set of task instances associated with this process instance
	 */
	private Set taskInstances = new HashSet();	
	private long state;
	private boolean locked = false;
	private Map taskPropertySets = new HashMap();
	
	
	public MockProcessInstance(IProcessDefinition processDef){
		this.processInstanceId = new Long(counter++);
		this.processDef = processDef;		
	}	
	/**
	 * @param taskInstances The taskInstances to set.
	 */
	public void setTaskInstances(Set taskInstances) {
		this.taskInstances = taskInstances;
	}

	/**
	 * @param processDef The processDef to set.
	 */
	public void setProcessDef(IProcessDefinition processDef) {
		this.processDef = processDef;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IProcessInstance#getProcessDef()
	 */
	public IProcessDefinition getProcessDef() throws DefinitionNotFoundException {		
		return processDef;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IProcessInstance#getProcessInstanceId()
	 */
	public Long getProcessInstanceId() {
		return processInstanceId;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IProcessInstance#getState()
	 */
	public long getState() {
		return state;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IProcessInstance#getTaskInstances()
	 */
	public Set getTaskInstances() {
		return taskInstances;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IProcessInstance#setState(long)
	 */
	public void setState(long state) {
		this.state = state;

	}

	/**
	 * returns a count of the task instances in this process
	 * instance that match the task definition and task instance state
	 * specified
	 * 
	 * @param taskDef
	 * @param expectedState
	 * @return
	 * @throws DefinitionNotFoundException
	 *
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	public int countInstances(MockTaskDef taskDef, long expectedState) throws DefinitionNotFoundException {
    	int x = 0;
    	for (Iterator it = taskInstances.iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockTaskInstance) {
    			MockTaskInstance ti = (MockTaskInstance) o;
    			if (ti.getTaskDefinition().equals(taskDef)) {
    				if(ti.getState()==expectedState) {
    					x++;
    				}
    			}
    		}
    	}
		return x;
    }

	/**
	 * returns a task instance on this process
	 * that is of the give task definition.
	 * 
	 * If more than one exists, the first found is returned
	 * 
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @param taskDef
	 * @param expectedState
	 * @return
	 * @throws DefinitionNotFoundException 
	 */
	public MockTaskInstance findTask(MockTaskDef taskDef, long expectedState) throws DefinitionNotFoundException {
		for (Iterator it = taskInstances.iterator();it.hasNext();) {
    		MockTaskInstance ti = (MockTaskInstance) it.next();
    		if (ti.getTaskDefinition().equals(taskDef)) {
    			if(ti.getState()==expectedState) {
    				return ti;
    			}
    		}
    	}
		return null;

	}

	/* (non-Javadoc)
	 * @see java.lang.Object#toString()
	 */
	public String toString() {
		return "MOCK-PI-ID "+ this.processInstanceId + " [" + this.processDef + "]";
	}

	/**
	 * @return Returns the locked status of this process instance.
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public boolean isLocked() {
		return locked;
	}

	/**
	 * @param locked TRUE to lock this process instance
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public void setLocked(boolean locked) {
		this.locked = locked;
	}

	/**
	 * @param instance
	 * @return
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public Map getTaskPropertySet(MockTaskInstance instance) {
		if (this.taskPropertySets.containsKey(instance)) {
			return (Map) this.taskPropertySets.get(instance);
		}		
		Map propertySet = new HashMap();
		this.taskPropertySets.put(instance,propertySet);
		return propertySet;
	}
}
