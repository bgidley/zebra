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
package com.anite.zebra.hivemind.api;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.hivemind.impl.Zebra;
import com.anite.zebra.hivemind.manager.TimeManager;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.taskAction.NoopHiveMindTaskAction;

public class TimedTaskRunnerTest extends TestCase {
	public void setUp() {
		Resource resource = new ClasspathResource(new DefaultClassResolver(),
				"META-INF/hivemodule_zebradefinitions.xml");
		RegistryManager.getInstance().getResources().add(resource);
	}

	public void testService() {

		TimedTaskRunner timedTaskRunner = (TimedTaskRunner) RegistryManager
				.getInstance().getRegistry().getService(
						"zebra.TimedTaskRunner", TimedTaskRunner.class);
		assertNotNull(timedTaskRunner);
	}

	public void testServiceContract() throws CreateProcessException,
			StartProcessException {
		Zebra zebra = (Zebra) RegistryManager.getInstance().getRegistry()
				.getService(Zebra.class);
		NoopHiveMindTaskAction.run = false;

		ZebraProcessInstance zpi = zebra
				.createProcessPaused("TestTimedTaskRunner");
		zebra.startProcess(zpi);
		// Should run up to manual activity.
		assertEquals(1, zpi.getHistoryInstances().size());

		TimedTaskRunner timedTaskRunner = (TimedTaskRunner) RegistryManager
				.getInstance().getRegistry().getService(
						"zebra.TimedTaskRunner", TimedTaskRunner.class);
		timedTaskRunner.scheduleTimedTask(zpi.getTaskInstances().iterator()
				.next(), 1, 0, null);

		TimeManager timeManager = (TimeManager) RegistryManager.getInstance()
				.getRegistry().getService(TimeManager.class);
		timedTaskRunner.runTasksForTime(timeManager.createOrFetchTime(1, 0));

		// The task we just queued should be run. Then the noopTask
		assertTrue(NoopHiveMindTaskAction.run);

	}
}
