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
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author martin.rouen
 */
public class TurbineAntelopeRoutingDefinitionTest extends TestCase {
	private Session session;

	private ZebraHelper zebraHelper;

	private AntelopeProcessDefinition processDefinition;

	private IAvalonDefsFactory definitionsFactory;

	private AntelopePropertyGroups propG;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		//get the database session (hibernate) like a adodb.connection object
		session = PersistenceLocator.getInstance().getCurrentSession();
		
		TurbineTestCase.initialiseTurbine();
		
		zebraHelper = ZebraHelper.getInstance();
		processDefinition = zebraHelper.getProcessDefinition("SimpleWorkflow");
	}

	public void testGetParallel() {
		boolean hasParallel = false;
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		while (router.hasNext()) {
			RoutingDefinition route = (RoutingDefinition) router.next();
			hasParallel = route.getParallel();
		}
		assertFalse("No Parallel", hasParallel);
	}

	public void testGetXmlId() {
		Long x = new Long(234);
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		AntelopeRoutingDefinition route = (AntelopeRoutingDefinition) router
				.next();
		route.setXmlId(x);
		assertEquals("No XML ID", route.getXmlId(), x);

	}

	public void testGetId() {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		AntelopeRoutingDefinition route = (AntelopeRoutingDefinition) router
				.next();
		assertTrue("No ID", route.getId().longValue() > 0);
	}

	/*
	 * Class under test for String getName()
	 */
	public void testGetName() {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		AntelopeRoutingDefinition route = (AntelopeRoutingDefinition) router
				.next();
		route.setName("test");

		assertTrue("No Name", route.getName().length() > 0);
		assertNotNull(route.getName());
		// Make sure we set it back to null otherwise it breaks things
		route.setName(null);
	}

	/*
	 * Class under test for ITaskDefinition getOriginatingTaskDefinition()
	 */
	public void testGetOriginatingTaskDefinition() {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		RoutingDefinition route = (RoutingDefinition) router.next();
		assertEquals(task, route.getOriginatingTaskDefinition());

	}

	/*
	 * Class under test for IPropertyGroups getPropertyGroups()
	 */
	public void testGetPropertyGroups() {
		propG = new AntelopePropertyGroups();
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		RoutingDefinition route = (RoutingDefinition) router.next();
		route.setPropertyGroups(propG);
		// Set propElement = propG.getPropertyElements();

		IPropertyGroups x = route.getPropertyGroups();
		assertTrue("No Property Groups", x.toString().length() > 0);
	}

	/*
	 * Class under test for String getConditionClass()
	 */
	public void testGetConditionClass() {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		RoutingDefinition route = (RoutingDefinition) router.next();
		assertNotNull("ConditionClass missing", route.getConditionClass());
	}

	/*
	 * Class under test for ITaskDefinition getDestinationTaskDefinition()
	 */
	public void testGetDestinationTaskDefinition() {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		Iterator router = task.getRoutingOut().iterator();
		AntelopeRoutingDefinition route = (AntelopeRoutingDefinition) router
				.next();
		TaskDefinition task2 = (TaskDefinition) route
				.getDestinationTaskDefinition();
		router = task2.getRoutingIn().iterator();

		route = (AntelopeRoutingDefinition) router.next();
		task = (TaskDefinition) route.getDestinationTaskDefinition();
		assertTrue(task.getName().length() > 0);

	}

}