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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author Eric Pugh
 *
 * TODO To change the template for this generated type comment go to
 * Window - Preferences - Java - Code Style - Code Templates
 */
public class MemoryTaskInstance implements ITaskInstance {

	private static Log log  = LogFactory.getLog(MemoryProcessInstance.class);
	private static Long taskInstanceCounter = new Long(1); 
	private Long taskInstanceId = null;
	private IProcessInstance processInstance;
	private IFOE foe;
	private ITaskDefinition taskDef;
	private long state;
	/**
	 * 
	 */
	public MemoryTaskInstance() {
		long temp = taskInstanceCounter.longValue();		
		taskInstanceId = new Long(temp);
		temp++;
		taskInstanceCounter = new Long(temp);
		log.info("Created MemoryTaskInstance id " + taskInstanceId);
	}

	/* 
	 * @see com.anite.zebra.core.states.api.ITaskInstance#getProcessInstance()
	 */
	public IProcessInstance getProcessInstance() {
		return processInstance;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.states.api.ITaskInstance#getFOE()
	 */
	public IFOE getFOE() {
		return foe;
	}


	public ITaskDefinition getTaskDefinition() throws DefinitionNotFoundException {
		return taskDef;
	}

	public Long getTaskInstanceId() {
		return taskInstanceId;
	}


	public long getState() {
		return state;
	}


	public void setState(long state) {
		this.state = state;

	}

	/**
	 * @param foe The foe to set.
	 */
	public void setFoe(IFOE foe) {
		this.foe = foe;
	}
	/**
	 * @param processInstance The processInstance to set.
	 */
	public void setProcessInstance(IProcessInstance processInstance) {
		this.processInstance = processInstance;
	}
	/**
	 * @param taskDef The taskDef to set.
	 */
	public void setTaskDef(ITaskDefinition taskDef) {
		this.taskDef = taskDef;
	}
}
