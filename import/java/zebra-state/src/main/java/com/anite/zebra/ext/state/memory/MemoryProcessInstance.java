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

import java.util.HashSet;
import java.util.Set;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * @author Eric Pugh
 *
 * TODO To change the template for this generated type comment go to
 * Window - Preferences - Java - Code Style - Code Templates
 */
public class MemoryProcessInstance implements IProcessInstance {
	
	private static Log log  = LogFactory.getLog(MemoryProcessInstance.class);
	private static Long processInstanceCounter = new Long(1); 
	private Long processInstanceId = null;
	private IProcessDefinition processDef = null;
	private Set taskInstances = new HashSet();	
	private long state;
	private boolean lock;
	
	/**
	 * @param taskInstances The taskInstances to set.
	 */
	public void setTaskInstances(Set taskInstances) {
		this.taskInstances = taskInstances;
	}
	public MemoryProcessInstance(){
		long temp = processInstanceCounter.longValue();		
		processInstanceId = new Long(temp);
		temp++;
		processInstanceCounter = new Long(temp);
		log.info("Created MemoryProcessInstance id " + processInstanceId);
		
	}
	/**
	 * @param processDef The processDef to set.
	 */
	public void setProcessDef(IProcessDefinition processDef) {
		this.processDef = processDef;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.IProcessInstance#getProcessDef()
	 */
	public IProcessDefinition getProcessDef() throws DefinitionNotFoundException {		
		return processDef;
	}
	/* 
	 * @see com.anite.zebra.core.states.api.IProcessInstance#getProcessInstanceId()
	 */
	public Long getProcessInstanceId() {
		return processInstanceId;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.IProcessInstance#getState()
	 */
	public long getState() {
		return state;
	}
	/* 
	 * @see com.anite.zebra.core.states.api.IProcessInstance#getTaskInstances()
	 */
	public Set getTaskInstances() {
		return taskInstances;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.IProcessInstance#isLocked()
	 */
	public boolean isLocked() {
		return lock;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.IProcessInstance#lock(boolean)
	 */
	public void lock(boolean lock) {
		this.lock = lock;
	}
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.IProcessInstance#setState(long)
	 */
	public void setState(long state) {
		this.state = state;

	}


}
