/*
 * Copyright 2005 Anite - Central Government Division
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
package org.apache.fulcrum.quartz.factory;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.ServiceImplementationFactory;
import org.quartz.Scheduler;

import junit.framework.TestCase;

public class QuartzSchedulerFactoryTest extends TestCase {

	public void testInitializeScheduler() {
		ServiceImplementationFactory quartzSchedulerFactory = (ServiceImplementationFactory) RegistryManager
				.getInstance().getRegistry().getService(
						"fulcrum.quartz.QuartzSchedulerFactory",
						ServiceImplementationFactory.class);
		assertNotNull(quartzSchedulerFactory);

		Scheduler scheduler = (Scheduler) RegistryManager.getInstance()
				.getRegistry().getService("fulcrum.quartz.Scheduler",
						Scheduler.class);
		assertNotNull(scheduler);
	}
}
