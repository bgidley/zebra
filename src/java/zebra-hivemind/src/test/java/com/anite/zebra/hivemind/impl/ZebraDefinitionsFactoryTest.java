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

package com.anite.zebra.hivemind.impl;

import java.util.Iterator;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;

/**
 * @author Ben.Gidley
 */
public class ZebraDefinitionsFactoryTest extends TestCase {

	private static final String SPLIT = "Split";

	private static final String DIDN_T_FIND_DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_ = "Didn't find Do you want to try and subprocess?";

	private static final String THE_END = "The End";

	private static final String DIDN_T_FIND_SUBPROCESS = "Didn't find SubProcess";

	private static final String SUBPROCESS = "SubProcess";

	private static final String DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_ = "Do you want to try and subprocess?";

	private static final String ENTER_SOME_DATA = "Enter some data";

	private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

	private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

	private ZebraDefinitionFactory zebraDefinitionFactory;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		
		Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_zebradefinitions.xml");
		RegistryManager.getInstance().getResources().add(resource);
		
		this.zebraDefinitionFactory = (ZebraDefinitionFactory) RegistryManager
				.getInstance().getRegistry().getService(
						"zebra.zebraDefinitionFactory",
						ZebraDefinitionFactory.class);
	}

	/**
	 * Check to see it if starts up by checking at least 1 process has loaded
	 */
	public void testStartUp() {
		assertNotNull(this.zebraDefinitionFactory.getProcessDefinitionByName(SIMPLEWORKFLOW));
	}

	/**
	 * Test to load up SimpleWorkflow and check the steps are present
	 * 
	 */
	public void testSimpleWorkflow() {
		ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
				.getProcessDefinitionByName(SIMPLEWORKFLOW);
		assertNotNull(processDefinition);
		assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

		assertTrue(processDefinition.getTaskDefinitions().size() == 5);

		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		assertEquals(WELCOME_TO_WORKFLOW, task.getName());

		Iterator router = task.getRoutingOut().iterator();
		RoutingDefinition route = (RoutingDefinition) router.next();

		task = (TaskDefinition) route.getDestinationTaskDefinition();
		assertEquals(ENTER_SOME_DATA, task.getName());

		router = task.getRoutingOut().iterator();
		route = (RoutingDefinition) router.next();
		task = (TaskDefinition) route.getDestinationTaskDefinition();
		assertEquals(DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_, task.getName());

		boolean foundIT = false;
		TaskDefinition subProcess = null;
		router = task.getRoutingOut().iterator();
		while (router.hasNext()) {

			route = (RoutingDefinition) router.next();
			task = (TaskDefinition) route.getDestinationTaskDefinition();
			if (task.getName().compareTo(SUBPROCESS) == 0) {
				foundIT = true;
				subProcess = task;
			}
		}
		assertTrue(DIDN_T_FIND_SUBPROCESS, foundIT);
		router = subProcess.getRoutingOut().iterator();

		// this one will loop

		route = (RoutingDefinition) router.next();
		task = (TaskDefinition) route.getDestinationTaskDefinition();

		assertEquals(THE_END, task.getName());
		// check back up the line
		foundIT = false;
		TaskDefinition subprocess = null;

		router = task.getRoutingIn().iterator();
		while (router.hasNext()) {

			route = (RoutingDefinition) router.next();
			task = (TaskDefinition) route.getOriginatingTaskDefinition();
			if (task.getName().compareTo(DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_) == 0) {
				foundIT = true;
				subprocess = task;
			}
		}
		assertNotNull(subprocess);
		assertTrue(DIDN_T_FIND_DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_, foundIT);

	}

	/**
	 * Test split workflow can be loaded and the steps are present
	 * 
	 * @throws DefinitionNotFoundException
	 * 
	 */
	public void testSplitWorkflow(){
		ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
				.getProcessDefinitionByName(SPLIT);
		assertNotNull(processDefinition);
		assertEquals(SPLIT, processDefinition.getName());
		// how many?
		assertTrue(processDefinition.getTaskDefinitions().size() == 6);
		// get the first task from process definition
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		// check the name is the same
		assertEquals("Manual Activity", task.getName());
		// create an iterator, assign it to get routingout
		Iterator router = task.getRoutingOut().iterator();
		// move up one
		RoutingDefinition route = (RoutingDefinition) router.next();
		// only one destination
		task = (TaskDefinition) route.getDestinationTaskDefinition();
		// check the name is the same
		assertEquals("Are they a pensioner", task.getName());
		// next is one of three
		boolean foundBored = false;
		boolean foundPension = false;
		boolean foundSurvey = false;
		boolean foundPensioner = false;
		TaskDefinition bored = null;
		TaskDefinition pension = null;
		TaskDefinition survey = null;
		TaskDefinition pensioner = null;
		router = task.getRoutingOut().iterator();
		while (router.hasNext()) {

			route = (RoutingDefinition) router.next();
			task = (TaskDefinition) route.getDestinationTaskDefinition();
			if (task.getName().compareTo("Ask if they are bored") == 0) {
				// this must also check for "Give them a customer satisfaction
				// survey"
				foundBored = true;
				bored = task;
				assertFalse("Paralell is wrong", route.getParallel());
			} else if (task.getName().compareTo(
					"Give them a customer satisfaction survey") == 0) {
				foundSurvey = true;
				survey = task;
				assertTrue("Paralell is wrong", route.getParallel());
			} else if (task.getName().compareTo("Ask if they have a pension") == 0) {
				foundPension = true;
				pension = task;
				assertFalse("Pension is not paralell", route.getParallel());

			} else if (task.getName().compareTo("Are they a pensioner") == 0) {
				foundPensioner = true;
				pensioner = task;
				assertFalse("Pensioner is not paralell", route.getParallel());

			} else {
				assertTrue(false);
			}

		}
		assertTrue(foundSurvey);
		assertTrue(foundPensioner);
		assertTrue(foundBored);
		assertTrue(foundPension);

		assertNotNull(pensioner);

		checkForletter(pension);
		checkForletter(bored);
		checkForletter(survey);
	}

	/**
	 * @param task
	 */
	private void checkForletter(TaskDefinition task) {
		Iterator router;
		RoutingDefinition route;
		router = task.getRoutingOut().iterator();
		route = (RoutingDefinition) router.next();

		task = (TaskDefinition) route.getDestinationTaskDefinition();
		assertEquals("Send them a letter", task.getName());
	}

	/**
	 * Test if we can load a process definition by name
	 * 
	 * @throws DefinitionNotFoundException
	 * 
	 */
	public void testGetProcessDefinitionByName()
			{
		ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
				.getProcessDefinitionByName(SIMPLEWORKFLOW);
		assertNotNull(processDefinition);
		assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

	}

	public void testGetProcessDefinitionByID() {
		ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
				.getProcessDefinitionByName(SIMPLEWORKFLOW);
		ZebraProcessDefinition processDefinitionById = this.zebraDefinitionFactory
				.getProcessDefinitionById(processDefinition.getId());

		assertEquals(processDefinition, processDefinitionById);
	}

	/**
	 * Test if we can load a task by ID
	 * 
	 * @throws DefinitionNotFoundException
	 */
	public void testGetTaskById() throws DefinitionNotFoundException {
		// load workflow

		Long taskID = null;
		ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
				.getProcessDefinitionByName(SIMPLEWORKFLOW);
		assertNotNull(processDefinition);
		assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

		assertTrue(processDefinition.getTaskDefinitions().size() == 5);
		// find a task
		TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
		// discover task name (we are using the Welcome to workflow one)
		assertEquals(WELCOME_TO_WORKFLOW, task.getName());

		// discover id
		taskID = task.getId();
		// call gettaskdefinitions, passing in id
		this.zebraDefinitionFactory.getTaskDefinition(taskID);
		assertEquals(WELCOME_TO_WORKFLOW, task.getName());
		// if it returns the same as task name, pass else fail

	}


}