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
import java.util.Set;

import junit.framework.TestCase;
import net.sf.hibernate.Session;

import org.apache.avalon.framework.component.ComponentException;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.impl.PropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author martin.rouen
 */
public class TurbineAntelopeProcessDefinitionTest extends TestCase {
	private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

	private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

	private Session session;

	private ZebraHelper zebraHelper;

	private AntelopeProcessDefinition processDefinition;

	private IAvalonDefsFactory definitionsFactory;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		super.setUp();
		//get the database session (hibernate) like a adodb.connection object
		session = PersistenceLocator.getInstance().getCurrentSession();
		// Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
		
		zebraHelper = ZebraHelper.getInstance();
		processDefinition = zebraHelper
				.getProcessDefinition(SIMPLEWORKFLOW);
	}

	/*
	 * Class under test for String getClassConstruct()
	 */
	public void testGetClassConstruct() {
		assertEquals(processDefinition.getClassConstruct(),"com.anite.antelope.zebra.processLifecycle.ProcessConstruct");
		
	}

	/*
	 * Class under test for String getClassDestruct()
	 */
	public void testGetClassDestruct() {
		assertEquals(processDefinition.getClassDestruct(),"com.anite.antelope.zebra.processLifecycle.ProcessDestruct");
		
	}

	/*
	 * Class under test for ITaskDefinition getFirstTask()
	 */
	public void testGetFirstTask() throws DefinitionNotFoundException,
			ComponentException {
		assertNotNull(processDefinition);
		assertEquals(WELCOME_TO_WORKFLOW,
				((AntelopeTaskDefinition) processDefinition.getFirstTask())
						.getName());
	}

	/*
	 * Class under test for Long getId()
	 */
	public void testGetId() {
		//check it has one and bigger than zero
		assertTrue(processDefinition.getId().longValue() > 0);
	}

	/*
	 * Class under test for String getName()
	 */
	public void testGetName() throws DefinitionNotFoundException,
			ComponentException {
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		assertEquals(WELCOME_TO_WORKFLOW, task.getName());
	}

	/*
	 * Class under test for IPropertyGroups getPropertyGroups()
	 */
	public void testGetPropertyGroups() throws DefinitionNotFoundException,
			ComponentException {
		//test for hard-coded string on PROPERTIES
		//IPropertyGroups propertyGroups =
		// processDefinition.getPropertyGroups();
		PropertyGroups propertyGroups = (PropertyGroups) processDefinition
				.getPropertyGroups();

		IProperties generalProperties = propertyGroups
				.getProperties("Visibility");

		assertEquals(generalProperties.getString("Display Name"), "Simple Workflow");
	}

	/*
	 * Class under test for Set getRoutingDefinitions()
	 */
	public void testGetRoutingDefinitions() throws DefinitionNotFoundException,
			ComponentException {
		//processDefinition.getRoutingDefinitions()
		Set routingDefinitions = processDefinition.getRoutingDefinitions();
		Iterator i = routingDefinitions.iterator();
		RoutingDefinition routingDefinition = (RoutingDefinition) i.next();
		
		assertEquals(routingDefinition.getParallel(), false);
	}

	/*
	 * Class under test for Set getTaskDefinitions()
	 */
	public void testGetTaskDefinitions() throws DefinitionNotFoundException,
			ComponentException {
		//processDefinition.getTaskDefinitions();
		
		Set taskDefinitions = processDefinition.getTaskDefinitions();
		Iterator i = taskDefinitions.iterator();
		TaskDefinition taskDefinition = (TaskDefinition) i.next();
		PropertyGroups propertyGroups = (PropertyGroups) taskDefinition
				.getPropertyGroups();
		IProperties taskProperties = propertyGroups.getProperties("(General Task Properties)");
		assertEquals(taskProperties.getBoolean("ShowInHistory"), true);

	}

	/*
	 * Class under test for Long getVersion()
	 */
public void testGetVersion() throws DefinitionNotFoundException, ComponentException {
		//processDefinition.getVersion();
		IProcessVersions versions =  processDefinition.getProcessVersions();
		versions.getLatestProcessVersion().getVersion();
		//Long version = processDefinition.getVersion();
		assertEquals((versions.getLatestProcessVersion().getVersion()),(processDefinition.getVersion()));
		//how do I tell which is the last one?
		
	}
	public void testGetInputs() {
	}

	public void testGetOutputs() throws DefinitionNotFoundException, ComponentException {
	//PROCESSDEFINITIONS.GETOUTPUTS
		
	//GETPROPERTYGROUPS - FIND ONE CALLED OUTPUTS.
		 IProperties outputs = processDefinition.getOutputs();
		 assertNotNull(outputs);

		
	}

	public void testGetPermissions() {
	}

	public void testGetDisplayName() {
	    String dispalyName = processDefinition.getDisplayName();
	    assertEquals("Simple Workflow", dispalyName);
	    
	}

	public void testGetDebugFlow() {
	}

	/*
	 * Class under test for IProcessVersions getProcessVersions()
	 */
	public void testGetProcessVersions() {
	}

	public void testSetVersions() {
	}

}