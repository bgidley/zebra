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

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author martin.rouen
 */
public class TurbineAntelopeTaskDefinitionTest extends TestCase {
	private AntelopeTaskDefinition taskDefinition;

	private Session session;

	private ZebraHelper zebraHelper;

	private AntelopeProcessDefinition processDefinition;

	private IAvalonDefsFactory definitionsFactory;

	private AntelopePropertyGroups propertyGroups;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		//get the database session (hibernate) like a adodb.connection object
		session = PersistenceLocator.getInstance().getCurrentSession();
		// Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();

		zebraHelper = ZebraHelper.getInstance();
		processDefinition = zebraHelper.getProcessDefinition("SimpleWorkflow");
		taskDefinition = (AntelopeTaskDefinition) processDefinition
				.getFirstTask();

	}

	public void testIsAuto() {
		assertFalse(taskDefinition.isAuto());
	}

	public void testGetSynchronise() {
		assertFalse(taskDefinition.getSynchronise());
	}

	public void testGetXmlId() {
		//assertTrue(taskDefinition.getXmlId().longValue() > 0);
	}

	//public void testSetXmlId() {
	//}

	/*
	 * Class under test for Long getId()
	 */
	public void testGetId() {
		assertTrue(taskDefinition.getId().longValue() > 0);
	}

	/*
	 * Class under test for String getClassConstruct()
	 */
	public void testGetClassConstruct() {
		assertNull(taskDefinition.getClassConstruct());
	}

	/*
	 * Class under test for String getClassDestruct()
	 */
	public void testGetClassDestruct() {
		assertNull(taskDefinition.getClassDestruct());
	}

	/*
	 * Class under test for String getClassName()
	 */
	public void testGetClassName() {
		assertNull(taskDefinition.getClassName());
	}

	/*
	 * Class under test for String getName()
	 */
	public void testGetName() {
		assertTrue(taskDefinition.getName().length() > 0);
	}

	/*
	 * Class under test for IPropertyGroups getPropertyGroups()
	 */
	public void testGetPropertyGroups() {
		propertyGroups = (AntelopePropertyGroups) processDefinition
				.getPropertyGroups();
		assertTrue(propertyGroups.getId().longValue() > 0);
	}

	/*
	 * Class under test for Set getRoutingIn()
	 */
	public void testGetRoutingIn() {
		taskDefinition = (AntelopeTaskDefinition) processDefinition
				.getFirstTask();
		Iterator router = taskDefinition.getRoutingOut().iterator();
		AntelopeRoutingDefinition route = (AntelopeRoutingDefinition) router
				.next();
		TaskDefinition task2 = (TaskDefinition) route
				.getDestinationTaskDefinition();
		assertNotNull(task2.getRoutingIn().iterator().next());

	}

	/*
	 * Class under test for Set getRoutingOut()
	 */
	public void testGetRoutingOut() {
		taskDefinition = (AntelopeTaskDefinition) processDefinition
				.getFirstTask();
		assertNotNull(taskDefinition.getRoutingOut());
	}

	public void testGetGeneralProperties() {
		taskDefinition.getGeneralProperties();
	}

	public void testGetScreenProperties() {
		taskDefinition.getScreenProperties();
	}

	public void testGetSubflowProperties() {
		taskDefinition.getSubflowProperties();
	}

	public void testGetInputs() {
		taskDefinition.getInputs();
	}

	public void testGetOutputs() {
		taskDefinition.getOutputs();
	}

	public void testGetShowInHistory() {
		assertTrue(taskDefinition.getShowInHistory());
	}

	public void testGetStaticPermissions() {
		assertTrue(taskDefinition.getStaticPermissionsString().length() >= 0); //$SUP-CSR$
	}

	public void testGetSubProcessName() {
		assertNull(taskDefinition.getSubProcessName());
	}

	public void testGetPushOutputs() {
		//assertFalse(taskDefinition.getPushOutputs());
	}

	public void testGetScreenName() {
		assertTrue(taskDefinition.getScreenName().toString().length() >= 0); //$SUP-CSR$
	}

	public void testGetAutoShow() {
		assertTrue(taskDefinition.getAutoShow());

	}

}