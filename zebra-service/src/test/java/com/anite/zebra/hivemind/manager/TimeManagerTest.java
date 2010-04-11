/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.manager;

import com.anite.zebra.hivemind.om.timedtask.Time;

public class TimeManagerTest extends BaseManagerTest<TimeManager> {

	public void testCreateOrFindTime() {

		TimeManager timeManager = (TimeManager) manager;

		Time time = timeManager.createOrFetchTime(0, 0);
		assertNotNull(time);

		assertNotNull(time.getId());

	}

	public void testTimeGetJobName() {

		TimeManager timeManager = (TimeManager) manager;

		Time time = timeManager.createOrFetchTime(0, 0);
		assertEquals(time.getJobName(), "00:00");
		
		time = timeManager.createOrFetchTime(1, 11);
		assertEquals(time.getJobName(), "01:11");

		time = timeManager.createOrFetchTime(11, 4);
		assertEquals(time.getJobName(), "11:04");
	}
}
