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

package com.anite.zebra.core.factory.api;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Matthew.Norris
 * 
 * State Factory interface.
 * 
 * A running process (and it's tasks) are persisted and accessed by the Engine via the States interface.
 * 
 */
public interface IStateFactory {

	/**
	 * Starts a transaction
	 *  
	 */
	public ITransaction beginTransaction()
		throws StateFailureException;

	/**
	 * Saves an object
	 * 
	 * @param aso
	 */
	public void saveObject(IStateObject aso)
		throws StateFailureException;
	/**
	 * Deletes an object
	 * 
	 * @param aso
	 */
	public void deleteObject(IStateObject aso)
		throws StateFailureException;
	/**
	 * loads an object
	 * 
	 * @param guid
	 * @return
	 */
	/*public IStateObject loadObject(Class theClass, long id)
		throws StateFailureException;
*/
	/**
	 * create a ProcessInstance using the specified ProcessDef 
	 * It is the factory responsibility to populate the ProcessInstanceId when this call returns
	 * 
	 * @param processDef
	 * @param guid
	 * @return new ProcessInstance
	 * @throws CreateObjectException
	 */
	public IProcessInstance createProcessInstance(
		IProcessDefinition processDef)
		throws CreateObjectException;

	/**
	 * create a TaskInstance of the specified TaskDef on the specified
	 * ProcessInstance
	 * 
	 * It is the factory responsibility to populate the TaskInstanceId when this call returns
	 * 
	 * @param taskDef
	 * @param processInstance
	 * @return new TaskInstance
	 * @throws CreateObjectException
	 */
	public ITaskInstance createTaskInstance(
		ITaskDefinition taskDef,
		IProcessInstance processInstance,
		IFOE foe)
		throws CreateObjectException;

	/**
	 * 
	 * Creates a new Flow of Execution object
	 * 
	 * @param processInstance
	 * @return new FOE
	 * @throws CreateObjectException
	 * 
	 */
	public IFOE createFOE(IProcessInstance processInstance) throws CreateObjectException;

    /**
     * Acquires a lock on the ProcessInstance. A ProcessInstance is locked by an
     * instance of the Zebra Engine during processing of Task Synchronisation.
     * 
     * A Process Instance is "locked" immediately when transitioning starts, and
     * is unlocked at the end of a transition sequence.
     * 
     * When an implementing class encounters a Process Instance that is 
     * already locked it should either:
     *    a) go into a "wait" loop
     *    b) throw a LockException
     * 
     * Whilst a ProcessInstance is locked, no modifications should be made to
     * either it's properties, or any of it's TaskInstances (including adding
     * any new TaskInstances).
     * 
     * Therefore it's useful to know which Engine instance is making this call
     *  to any given state factory.
     * 
     * @return
     * @param processInstance
     * @throws LockException
     */
    public void acquireLock(IProcessInstance processInstance, IEngine engine) throws LockException;

    /**
     * Releases the exclusive lock on a ProcessInstance.
     * Again it's useful to know which Engine instance is making this call.
     * @param processInstance
     * @throws LockException
     */
    public void releaseLock(IProcessInstance processInstance, IEngine engine) throws LockException;
}
