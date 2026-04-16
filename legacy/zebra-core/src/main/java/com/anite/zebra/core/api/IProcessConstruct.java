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

import com.anite.zebra.core.exceptions.ProcessConstructException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * Process Construct Interface
 * Implement this interface to create a class the Engine will call
 * before a process instance starts running 
 *  - ProcessInstance change in state from STATE_CREATED to STATE_INITIALISING
 *  After the ProcessConstruct class has run, the ProcessInstance state will be STATE_RUNNING
 * 
 * @author Matthew.Norris
 */
public interface IProcessConstruct {

	/**
	 * Called by the Engine when startProcess is invoked.
	 * Put any ProcessInstance initialisation code here.
	 * 
	 * @param ipi
	 * @throws ProcessConstructException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void processConstruct(IProcessInstance ipi) throws ProcessConstructException;
	
}
