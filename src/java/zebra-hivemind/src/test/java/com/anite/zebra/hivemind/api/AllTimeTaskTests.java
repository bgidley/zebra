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

import com.anite.zebra.hivemind.manager.FiredTimedTaskManagerTest;
import com.anite.zebra.hivemind.manager.TimeManagerTest;
import com.anite.zebra.hivemind.manager.TimedTaskManagerTest;

import junit.framework.Test;
import junit.framework.TestSuite;

public class AllTimeTaskTests {

	public static Test suite() {
		TestSuite suite = new TestSuite("Test for com.anite.zebra.hivemind.api");
		//$JUnit-BEGIN$
		suite.addTestSuite(TimedTaskRunnerTest.class);
		//$JUnit-END$
		suite.addTestSuite(FiredTimedTaskManagerTest.class);
		suite.addTestSuite(TimedTaskManagerTest.class);
		suite.addTestSuite(TimeManagerTest.class);
		return suite;
	}

}
