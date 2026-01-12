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

package com.anite.zebra.core.api;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author Matthew.Norris
 */
public interface IEngine {
	
	/**
	 * transitions the specified task
	 * @param taskInstance
	 * @throws TransitionException
	 */
	public void transitionTask(ITaskInstance taskInstance) throws TransitionException;
	/**
	 * Creates the a ProcessInstance of the specified process definition.
	 * To start the process, call startProcess.  
	 * @param processDef
	 * @return the created ProcessInstance
	 * @throws CreateProcessException
	 */
	public IProcessInstance createProcess(IProcessDefinition processDef) throws CreateProcessException;
	
	/**
	 * Starts a process (creates the first task and 
	 * starts transitioning the workflow) 
	 * that was created using createProcess. 
	 * 
	 * @param processInstance
	 * @throws StartProcessException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void startProcess(IProcessInstance processInstance) throws StartProcessException;
		
}
