/*
 * Copyright 2005 Anite - Enforcement & Security
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
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author Matthew.Norris
 * Created on 22-Sep-2005
 */
public class WaitForKick implements ITaskAction {

	public static final String STOP_SLEEPING = "Wakey wakey";
	public static final String CHECK_INTERVAL = "Whassatnoise?";
	private static final Long DEFAULT_CHECK_INTERVAL = new Long(250);
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.api.ITaskAction#runTask(com.anite.zebra.core.state.api.ITaskInstance)
	 */
	public void runTask(ITaskInstance taskInstance) throws RunTaskException {
		MockTaskInstance mti = (MockTaskInstance) taskInstance;
		Long checkInterval;
		if (mti.getPropertySet().containsKey(CHECK_INTERVAL)) {
			checkInterval = (Long) mti.getPropertySet().get(CHECK_INTERVAL);
		} else {
			checkInterval = DEFAULT_CHECK_INTERVAL;
		}
		while (!mti.getPropertySet().containsKey(STOP_SLEEPING)) {
			try {
				Thread.sleep(checkInterval.longValue());
			} catch (InterruptedException e) {
				throw new RunTaskException("Someone rudely interrupted me!");
			}
		}
		mti.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
	}

}
