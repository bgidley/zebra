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
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * Called by the Engine when a process has no more tasks.
 * The ProcessInstance state is STATE_COMPLETING.
 * Once the ProcessDestruct class has run, the ProcessInstance state becomes STATE_COMPLETE.
 * 
 * @author Matthew.Norris
 */
public interface IProcessDestruct {
	/**
	 * Called by the Engine when the ProcessInstance is in a state of STATE_COMPLETING.
	 * Place any ProcessInstance tidy-up code in the processDestruct routine.
	 * @param processInstance
	 * @throws DestructException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void processDestruct(IProcessInstance processInstance) throws DestructException;
}
