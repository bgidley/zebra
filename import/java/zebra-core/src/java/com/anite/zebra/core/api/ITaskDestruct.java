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

import com.anite.zebra.core.exceptions.DestructException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Optional class that is called by the Engine after task completion.
 * This call happens when the TaskInstance state is STATE_COMPLETING.
 * 
 * After a successful call to this class the TaskInstance state is STATE_COMPLETE.
 * 
 * @TODO: This functionality is currently NOT IMPLEMENTED and may be removed
 * 
 * @author Matthew.Norris
 */
public interface ITaskDestruct {
	/**
	 * Called by the Engine before a TaskInstance is completed.
	 * 
	 * @param taskInstance
	 * @throws DestructException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void taskDestruct(ITaskInstance taskInstance) throws DestructException;
	
}
