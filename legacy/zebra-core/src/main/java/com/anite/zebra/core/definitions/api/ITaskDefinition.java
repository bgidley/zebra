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

import java.util.Set;


/**
 * @author Matthew Norris
 */
public interface ITaskDefinition {
	/**
	 * @return the ID of this TaskDefinition
	 */
	public Long getId();
	/**
	 * indicates if the task runs automatically as soon as it is created by the engine
	 * @return TRUE if the engine should automatically transition the task 
	 */
	public boolean isAuto();
	/**
	 * 
	 * This is the class that must conform to the ITaskAction interface that is called when the task is transitioned by the Engine. Can be null.
	 * 
	 * @return the name of an ITaskAction class
	 */
	public String getClassName();
	/**
	 * indicates whether this task is a Synchronise task
	 * @return TRUE if is a Synchronise task
	 */
	public boolean isSynchronised();
	
	/**
	 * @return Returns the ProcessDef this TaskDef belongs to
	 * @todo check and see if this method is ever used.  I searched through
	 * CTMS and never saw a usage.  Except in one Avalon componetn that loaded it up
	 * and could have done it directly because it had the process def id.
	 */	
	//public IProcessDefinition getProcessDef();

	/**
	 * returns the Outbound RoutingDefs from this TaskDef
	 * @return Set of RoutingDef objects
	 */
	public Set getRoutingOut();
	
	/**
	 * returns the inbound routingdefs leading to this TaskDef 
	 * @return Set of RoutingDef objects
	 */
	public Set getRoutingIn(); 
	
	/**
	 * returns the class name to run when the task is first created
	 * @return name of an ITaskConstruct class
	 */
	public String getClassConstruct();
	/**
	 * returns the name of the class to run when the task has completed
	 * @TODO: Currently NOT IMPLEMENT and may be removed in later releases
	 * @return name of an ITaskDestruct class
	 */
	public String getClassDestruct();
}