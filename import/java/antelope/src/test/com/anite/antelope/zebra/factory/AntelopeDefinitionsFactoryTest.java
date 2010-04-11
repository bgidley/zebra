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

package com.anite.antelope.zebra.factory;

import java.util.Iterator;

import org.apache.fulcrum.testcontainer.BaseUnitTest;

import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author Ben.Gidley
 */
public class AntelopeDefinitionsFactoryTest extends BaseUnitTest {

    private static final String SRC_TEST_ZEBRACOMPONENTCONFIGURATION_XML = "src/test/ZebraComponentConfiguration.xml";

    private static final String DIDN_T_FIND_DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_ = "Didn't find Do you want to try and subprocess?";

    private static final String THE_END = "The End";

    private static final String DIDN_T_FIND_SUBPROCESS = "Didn't find SubProcess";

    private static final String SUBPROCESS = "SubProcess";

    private static final String DO_YOU_WANT_TO_TRY_AND_SUBPROCESS_ = "Do you want to try and subprocess?";

    private static final String ENTER_SOME_DATA = "Enter some data";

    private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

    private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

    private IAvalonDefsFactory definitionsFactory;

    /**
     * @param testName
     */
    public AntelopeDefinitionsFactoryTest(String testName) {
        super(testName);
    }

    /*
     * @see TestCase#setUp()
     */
    protected void setUp() throws Exception {
        super.setUp();
        definitionsFactory = (IAvalonDefsFactory) this
                .lookup(IAvalonDefsFactory.class.getName());
    }

    /**
     * Check to see it if starts up by checking at least 1 process has loaded
     */
    public void testStartUp() {
        assertTrue(definitionsFactory.getAllProcessDefinitions().size() > 0);

    }

    /**
     * Test to load up SimpleWorkflow and check the steps are present
     * 
     * @throws DefinitionNotFoundException
     *  
     */
    public void testSimpleWorkflow() throws DefinitionNotFoundException {
        ProcessDefinition processDefinition = (ProcessDefinition) definitionsFactory
                .getProcessDefinition(SIMPLEWORKFLOW);
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

        //		this one will loop

        route = (RoutingDefinition) router.next();
        task = (TaskDefinition) route.getDestinationTaskDefinition();

        assertEquals(THE_END, task.getName());
        //check back up the line
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
    public void testSplitWorkflow() throws DefinitionNotFoundException {
        ProcessDefinition processDefinition = (ProcessDefinition) definitionsFactory
                .getProcessDefinition("Split");
        assertNotNull(processDefinition);
        assertEquals("Split", processDefinition.getName());
        // how many?
        assertTrue(processDefinition.getTaskDefinitions().size() == 6);
        //get the first task from process definition
        TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
        //check the name is the same
        assertEquals("Manual Activity", task.getName());
        //create an iterator, assign it to get routingout
        Iterator router = task.getRoutingOut().iterator();
        //move up one
        RoutingDefinition route = (RoutingDefinition) router.next();
        //only one destination
        task = (TaskDefinition) route.getDestinationTaskDefinition();
        //check the name is the same
        assertEquals("Are they a pensioner", task.getName());
        //next is one of three
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
                //this must also check for "Give them a customer satisfaction
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
            throws DefinitionNotFoundException {
        ProcessDefinition processDefinition = (ProcessDefinition) definitionsFactory
                .getProcessDefinition(SIMPLEWORKFLOW);
        assertNotNull(processDefinition);
        assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

    }

    public void testGetProcessDefinitionByID() throws DefinitionNotFoundException {
        AntelopeProcessDefinition processDefinition = (AntelopeProcessDefinition) definitionsFactory
                .getProcessDefinition(SIMPLEWORKFLOW);
        AntelopeProcessDefinition processDefinitionById = (AntelopeProcessDefinition) definitionsFactory.getProcessDefinition(processDefinition.getId());
        
        assertEquals(processDefinition, processDefinitionById);
    }

    /**
     * Test if we can load a task by ID
     * 
     * @throws DefinitionNotFoundException
     */
    public void testGetTaskById() throws DefinitionNotFoundException {
        //load workflow

        Long taskID = null;
        ProcessDefinition processDefinition = (ProcessDefinition) definitionsFactory
                .getProcessDefinition(SIMPLEWORKFLOW);
        assertNotNull(processDefinition);
        assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

        assertTrue(processDefinition.getTaskDefinitions().size() == 5);
        //find a task
        TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
        //discover task name (we are using the Welcome to workflow one)
        assertEquals(WELCOME_TO_WORKFLOW, task.getName());

        //discover id
        taskID = task.getId();
        //call gettaskdefinitions, passing in id
        definitionsFactory.getTaskDefinition(taskID);
        assertEquals(WELCOME_TO_WORKFLOW, task.getName());
        //if it returns the same as task name, pass else fail

    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.fulcrum.testcontainer.BaseUnitTest#getConfigurationFileName()
     */
    protected String getConfigurationFileName() {
        return SRC_TEST_ZEBRACOMPONENTCONFIGURATION_XML;

    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.fulcrum.testcontainer.BaseUnitTest#getRoleFileName()
     */
    protected String getRoleFileName() {

        return null;
    }
}