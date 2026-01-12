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

import com.anite.zebra.core.exceptions.TaskConstructException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Optional class that is called by the Engine before a TaskInstance is started.
 * This call happens when the TaskInstance state is STATE_INITIALISING.
 * 
 * After a successful call to this class the TaskInstance state is STATE_READY.
 * 
 * @author Matthew.Norris
 */
public interface ITaskConstruct {
	/**
	 * Called by the Engine before a TaskInstance is started.
	 * 
	 * @param taskInstance
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 * @throws TaskConstructException
	 */
	public void taskConstruct(ITaskInstance taskInstance) throws TaskConstructException;
	
}
