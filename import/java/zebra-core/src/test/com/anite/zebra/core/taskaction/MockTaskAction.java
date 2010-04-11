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

package com.anite.zebra.core.taskaction;

import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.processdef.ClassExceptionProcess;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class MockTaskAction implements ITaskAction {
	private int runCount =0;
	
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.api.ITaskAction#runTask(com.anite.zebra.core.state.api.ITaskInstance)
	 */
	public void runTask(ITaskInstance taskInstance) throws RunTaskException {
		runCount++;
		IProcessDefinition pd;
		try {
			pd = taskInstance.getProcessInstance().getProcessDef();
		} catch (Exception e) {
			throw new RunTaskException(e);
		}
		if (pd instanceof ClassExceptionProcess) {
			ClassExceptionProcess cep = (ClassExceptionProcess) pd;
			if (cep.failTaskAction) {
				throw new RunTaskException("Instructed to FAIL");
			}
		}
		taskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
	}

	/**
	 * @return
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public int getRunCount() {
		return runCount;
	}

}
