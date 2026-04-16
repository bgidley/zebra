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

import java.sql.Date;
import java.util.Iterator;

import junit.framework.TestCase;
import net.sf.hibernate.Session;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.utils.CalendarHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;

/**
 * @author martin.rouen
 */
public class TurbineAntelopeTaskInstanceHistoryTest extends TestCase {
	private AntelopeTaskInstanceHistory taskInstanceHistory;
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
		zebraHelper.getEngine().transitionTask(taskInstance);
		taskInstanceIterator = processInstance.getHistoryInstances().iterator();
		taskInstanceHistory = (AntelopeTaskInstanceHistory) taskInstanceIterator.next();
		
	}

	/*
	 * Class under test for void AntelopeTaskInstanceHistory()
	 */
	public void testAntelopeTaskInstanceHistory() {
		assertNotNull(taskInstanceHistory);
	}

	/*
	 * Class under test for void AntelopeTaskInstanceHistory(AbstractAntelopeTaskInstance)
	 */
	public void testAntelopeTaskInstanceHistoryAbstractAntelopeTaskInstance() {
		assertTrue(taskInstanceHistory.getTaskInstanceId().longValue()>0);
	}

	public void testGetDateCompleted() {
		
		taskInstanceHistory.setDateCompleted(CalendarHelper.getInstance().getSqlDate());
		assertNotNull(taskInstanceHistory.getDateCompleted());
	}


	public void testGetShowInHistory() {
		Boolean z = new Boolean("true");
		taskInstanceHistory.setShowInHistory(z);
		z=taskInstanceHistory.getShowInHistory();
		assertTrue(z.booleanValue());
	}


}