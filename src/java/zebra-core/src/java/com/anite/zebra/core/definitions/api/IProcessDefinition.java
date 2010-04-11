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

package com.anite.zebra.core.definitions.api;

/**
 * @author Matthew.Norris
 */
public interface IProcessDefinition {
	/**
	 * @return Returns the taskDefs.
	 */
	public ITaskDefinitions getTaskDefs();
	/**
	 * @return Returns the routingDefs.
	 */
	public IRoutingDefinitions getRoutingDefs();

	/**
	 * returns the first task in the process (the one to start the process it
	 * with)
	 * 
	 * @return
	 */
	public ITaskDefinition getFirstTask();

	/**
	 * returns the constructor class name - this class is called after the
	 * process is initialised, but before the first task in the process is run.
	 * 
	 * should be null if there is no constructor for the process
	 * 
	 * @return
	 */
	public String getClassConstruct();

	/**
	 * returns the destructor class name - this class is called after the last
	 * task in the process has completed, but before the process is marked as
	 * "complete".
	 * 
	 * should be null if there is no destructor for the process
	 * 
	 * @return
	 */
	public String getClassDestruct();
	


}