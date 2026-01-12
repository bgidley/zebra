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

package com.anite.zebra.core.state.api;

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;


/**
 * @author Matthew.Norris
 */
public interface ITaskInstance extends IStateObject {
	/**
	 * ORD  WHEN				STATE
	 *  1	AFTER CREATION		STATE_AWAITINGSYNC
	 *	2	AFTER CREATION		STATE_AWAITINGINITIALISATION
	 *	3	DURING INIT			STATE_INITIALISING
	 *	4	AFTER INIT			STATE_READY
	 *	5	DURING TASKACTION	STATE_RUNNING
	 *	6	AFTER TASKACTION	STATE_ERRORROUTING
	 *	7	AFTER TASKACTION	STATE_AWAITINGCOMPLETE
	 *	8	DURING DESTRUCT		STATE_COMPLETING
	 *	9	AFTER DESTRUCT		STATE_COMPLETE
	 *
	 *	STATE_AWAITINGSYNC occurs when a SYNC Task is
	 *	 first created. When the SYNC task can be run
	 *   (i.e. nothing is blocking it) it moves to 
	 *   STATE_AWAITINGINITALISATION (or STATE_READY 
	 *   if there is no CONSTRUCTOR specified).
	 *   
	 *  STATE_ERR_ROUTING only occurs if the engine 
	 *   catches an Exception after the task has been 
	 *   transitioned, when routing is being run.
	 */
	public static final long STATE_RUNNING = 1;
	public static final long STATE_COMPLETE = 2;
	public static final long STATE_READY = 3;
	public static final long STATE_COMPLETING = 4;
	public static final long STATE_INITIALISING = 5;
	public static final long STATE_ERRORROUTING = 6;
	public static final long STATE_AWAITINGINITIALISATION = 7;
	public static final long STATE_AWAITINGCOMPLETE = 8;
	public static final long STATE_AWAITINGSYNC = 9;
	
	
	
	/**
	 * ProcessInstance this TaskInstance belongs to
	 * @return
	 */
	public IProcessInstance getProcessInstance();
	/**
	 * Flow of Execution this TaskInstance is running on
	 * @return
	 */
	public IFOE getFOE();
	/**
	 * Task Definition behind this Task Instance
	 * @return
	 * @throws DefinitionNotFoundException
	 */
	public ITaskDefinition getTaskDefinition() throws DefinitionNotFoundException;
	/**
	 * Unique ID of this Task Instance
	 * @return
	 */
	public Long getTaskInstanceId();
	
	/**
	 * Current State of this Task Instance. See STATE constants in this class.
	 * @return
	 */
	public long getState();
	public void setState(long state);
}
