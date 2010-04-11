package com.anite.zebra.test;

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

import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.ext.state.memory.MemoryStateFactory;

/**
 * @author Matthew.Norris
 */
public class MemoryWorkflowTest extends CompatibilityWorkflowTestCase {

	public IStateFactory createStateFactory(){
		return new MemoryStateFactory();
	}
	public void postTestSimpleWorkflow() throws Exception{
		ITaskInstance taskInstance1 = (ITaskInstance)MemoryStateFactory.getAllTaskInstances().get(new Long(1));
		assertNotNull(taskInstance1);
		assertEquals(ITaskInstance.STATE_COMPLETE,taskInstance1.getState());
	}
}