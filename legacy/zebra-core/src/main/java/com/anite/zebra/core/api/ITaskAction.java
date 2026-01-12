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

import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * When a TaskInstance transitions an optional java class can be called to 
 * perform an activity. This class is called after any Synchronisation has 
 * taken place, and after any TaskConstruct class has been called.
 * 
 * Before this class is called the TaskInstance state changes to STATE_RUNNING.
 * 
 * If this class changes the TaskInstance state to STATE_AWAITINGCOMPLETION
 * the Engine will continue to transition the workflow process once the call completes.
 * 
 * If this class does not alter the TaskInstance state you need to alter the
 * TaskInstance state to STATE_AWAITINGCOMPLETION and call the transitionTask 
 * method on the Engine at a later time in order to progress the Process.
 * 
 * @author Matthew.Norris
 */
public interface ITaskAction {

	/**
	 * Called by the Engine when a task is being run.
	 * Setting the TaskInstance state to STATE_AWAITINGCOMPLETION in this routine
	 * will allow the Engine to complete the transition of this task.
	 * 
	 * If this routine kicks off an asychronous operation you can return immediately 
	 * and inform the Engine at a later time that the Task has completed.
	 * 
	 * @param taskInstance
	 * @throws RunTaskException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void runTask(ITaskInstance taskInstance) throws RunTaskException;
	
}
