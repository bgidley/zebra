/*
 * Copyright 2004 Anite - Central Government Division
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
package com.anite.antelope.zebra.om;

import java.util.Hashtable;
import java.util.Iterator;
import java.util.Map;

import junit.framework.TestCase;
import net.sf.hibernate.Session;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;

/**
 * @author martin.rouen
 */
public class TurbineAntelopeTaskInstanceTest extends TestCase {
	private AntelopeTaskInstance taskInstance;

	private AntelopeProcessInstance processInstance;

	private Iterator taskInstanceIterator;

	private ZebraHelper zebraHelper;

	private Session session;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {

		TurbineTestCase.initialiseTurbine();
	    
		zebraHelper = ZebraHelper.getInstance();
		processInstance = zebraHelper.createProcessPaused("SimpleWorkflow");
		zebraHelper.getEngine().startProcess(processInstance);
		taskInstanceIterator = processInstance.getTaskInstances().iterator();
		taskInstance = (AntelopeTaskInstance) taskInstanceIterator.next();

	}

	/*
	 * Class under test for void AntelopeTaskInstance()
	 */
	public void testAntelopeTaskInstance() {
		assertNotNull(taskInstance);
	}

	/*
	 * Class under test for void
	 * AntelopeTaskInstance(AbstractAntelopeTaskInstance)
	 */
	public void testAntelopeTaskInstanceAbstractAntelopeTaskInstance() {
		assertTrue(taskInstance.getTaskInstanceId().longValue()>0);
	}

	public void testGetPropertySetEntries() {
		Map x = new Hashtable();
		taskInstance.setPropertySet(x);
		// int y = x.hashCode();
		assertNotNull(taskInstance.getPropertySet());
	}

}