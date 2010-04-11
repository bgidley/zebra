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

import java.util.Iterator;

import junit.framework.TestCase;
import net.sf.hibernate.Session;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;

/**
 * @author martin.rouen
 * 
  */
public class TurbineAntelopeFOETest extends TestCase {

	private static final String SIMPLE_WORKFLOW = "SimpleWorkflow";

	private Session session;

	private ZebraHelper zebraHelper;

	/*
	 */

	protected void setUp() throws Exception {
		super.setUp();
		//get the database session (hibernate) like a adodb.connection object
		session = PersistenceLocator.getInstance().getCurrentSession();
		// Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
		
		zebraHelper = ZebraHelper.getInstance();
	}

	public void testGetProcessInstance() throws NestableException,
			StartProcessException, TransitionException, ComponentException, net.sf.hibernate.exception.NestableException {

		AntelopeProcessInstance processInstance = zebraHelper
				.createProcessPaused(SIMPLE_WORKFLOW);
		assertNotNull(processInstance);

		zebraHelper.getEngine().startProcess(processInstance);
		Iterator taskInstanceIterator = processInstance.getTaskInstances()
				.iterator();

		// There should be only 1 task (Welcome to Workflow)
		AntelopeTaskInstance welcomeToWorkflowTask = (AntelopeTaskInstance) taskInstanceIterator
				.next();
		assertNotNull(welcomeToWorkflowTask);
		AntelopeFOE antelopeFOE = (AntelopeFOE) welcomeToWorkflowTask.getFOE();
		assertEquals(welcomeToWorkflowTask.getProcessInstance(), antelopeFOE
				.getProcessInstance());
		AntelopeProcessInstance processInstance2 = zebraHelper
				.createProcessPaused(SIMPLE_WORKFLOW);
		antelopeFOE.setProcessInstance(processInstance2);
		assertEquals(processInstance2, antelopeFOE.getProcessInstance());

	}

	public void testGetAntelopeFoeID() throws NestableException,
			StartProcessException, ComponentException, net.sf.hibernate.exception.NestableException {
		AntelopeProcessInstance processInstance = zebraHelper
				.createProcessPaused(SIMPLE_WORKFLOW);
		assertNotNull(processInstance);

		zebraHelper.getEngine().startProcess(processInstance);
		Iterator taskInstanceIterator = processInstance.getTaskInstances()
				.iterator();

		// There should be only 1 task (Welcome to Workflow)
		AntelopeTaskInstance welcomeToWorkflowTask = (AntelopeTaskInstance) taskInstanceIterator
				.next();
		assertNotNull(welcomeToWorkflowTask);
		AntelopeFOE antelopeFOE = (AntelopeFOE) welcomeToWorkflowTask.getFOE();
		assertTrue(antelopeFOE.getAntelopeFoeID().intValue() > 0);
	}

}