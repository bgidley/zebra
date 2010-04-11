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

package com.anite.antelope.zebra.helper;

import java.util.Iterator;

import junit.framework.TestCase;
import net.sf.hibernate.HibernateException;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;

/**
 * Run a workflow from End to end
 * @author John Rae
 */
public class TurbineAntelopeRunWorkflowTest extends TestCase {
    private static final String GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY = "Give them a customer satisfaction survey";

    private static final String ASK_IF_THEY_HAVE_A_PENSION = "Ask if they have a pension";

    private static final String ASK_IF_THEY_ARE_BORED = "Ask if they are bored";

    private static final String SEND_THEM_A_LETTER = "Send them a letter";

    private static final String ARE_THEY_A_PENSIONER = "Are they a pensioner";

    private static final String YES = "Yes";

    private static final String NO = "No";

    private static final String SHALL_WE_DO_IT_AGAIN = "Shall we do it again";

    private static final String MANUAL_ACTIVITY = "Manual Activity";

    private static final String THE_END = "The End";

    private static final String SUBPROCESS = "SubProcess";

    private static final String SUBPROCESS_TASK = "SubProcess Task";

    private static final String DO_YOU_WANT_TO_TRY_AND_SUBPROCESS = "Do you want to try and subprocess?";

    private static final String ENTER_SOME_DATA = "Enter some data";

    private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

    private static final String SIMPLE_WORKFLOW = "SimpleWorkflow";

    private static final String SPLIT_WORKFLOW = "Split";

    private static Log log = LogFactory.getLog(TurbineAntelopeRunWorkflowTest.class);

    private ZebraHelper zebraHelper;

    private AntelopeProcessInstance processInstance;

    private Iterator taskInstanceIterator;

    protected void setUp() throws Exception {

        TurbineTestCase.initialiseTurbine();

        zebraHelper = ZebraHelper.getInstance();
    }

    public void testRunSimpleWorkflow() throws TransitionException,
            ComponentException, PersistenceException, HibernateException,
            NestableException,
            org.apache.commons.lang.exception.NestableException {

        runSimpleWorkflow(YES);
        runSimpleWorkflow(NO);
    }

    public void testRunSplitWorkflow() throws ComponentException,
            StartProcessException, NestableException, TransitionException {

        runSplitWorkflow(YES);
        runSplitWorkflow(NO);
        runSplitWorkflow(SHALL_WE_DO_IT_AGAIN);
    }

    /**
     * @throws NestableException
     * @throws TransitionException
     * @throws ComponentException
     * @throws org.apache.commons.lang.exception.NestableException
     * @throws HibernateException
     * @throws PersistenceException
     */
    private void runSimpleWorkflow(String test) throws NestableException,
            TransitionException, ComponentException, PersistenceException,
            HibernateException,
            org.apache.commons.lang.exception.NestableException {
        log.debug("testing Simple Workflow");
        
        processInstance = zebraHelper.createProcessPaused(SIMPLE_WORKFLOW);
        assertNotNull(processInstance);

        zebraHelper.getEngine().startProcess(processInstance);//get process instance

        testTaskDef(WELCOME_TO_WORKFLOW);

        testTaskDef(ENTER_SOME_DATA);

        testTaskDef(DO_YOU_WANT_TO_TRY_AND_SUBPROCESS, test);

        if (test == YES) {
            testTaskDef(SUBPROCESS_TASK,
                    (AntelopeProcessInstance) processInstance
                            .getRunningChildProcesses().get(0));
        }

        testTaskDef(THE_END);

    }

    public void runSplitWorkflow(String test) throws ComponentException,
            StartProcessException, NestableException, TransitionException {
        log.debug("testing Split workflow");

        processInstance = zebraHelper.createProcessPaused(SPLIT_WORKFLOW);
        assertNotNull(processInstance);
        
        zebraHelper.getEngine().startProcess(processInstance);//get process instance //already done once

        testTaskDef(MANUAL_ACTIVITY);

        testTaskDef(ARE_THEY_A_PENSIONER, test);

        if (test == YES) {
            testDualTaskDef(ASK_IF_THEY_ARE_BORED,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY);
            testDualTaskDef(SEND_THEM_A_LETTER, SEND_THEM_A_LETTER);

        } else if (test == NO) {
            testDualTaskDef(ASK_IF_THEY_HAVE_A_PENSION,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY);
            testDualTaskDef(SEND_THEM_A_LETTER, SEND_THEM_A_LETTER);

        } else if (test == SHALL_WE_DO_IT_AGAIN) {
            testDualTaskDef(ARE_THEY_A_PENSIONER,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY);//just do this once but in reality it would repeat infinitely
            testTripleTaskDef(ARE_THEY_A_PENSIONER,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY,
                    SEND_THEM_A_LETTER);

        }

    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testTaskDef(String taskName,
            AntelopeProcessInstance antelopeProcessInstance)
            throws TransitionException, ComponentException {
        log.debug("testing task");
        //get process
        //check correct process
        //advance flow
        assertEquals(antelopeProcessInstance.getTaskInstances().size(), 1);
        taskInstanceIterator = antelopeProcessInstance.getTaskInstances()
                .iterator();
        AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        assertNotNull(task);
        assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition())
                .getName(), taskName);
        zebraHelper.getEngine().transitionTask(task);
    }

    private void testTaskDef(String taskName) throws TransitionException,
            ComponentException {
        testTaskDef(taskName, processInstance);
    }

    /**
     * @param taskName
     * @param test
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions that take a parameter for routing
     */
    private void testTaskDef(String taskName, String test)
            throws TransitionException, ComponentException {
        log.debug("testing task");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 1);
        taskInstanceIterator = processInstance.getTaskInstances().iterator();
        AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        assertNotNull(task);
        assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition())
                .getName(), taskName);
        task.setRoutingAnswer(test);
        zebraHelper.getEngine().transitionTask(task);
    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testDualTaskDef(String taskName, String otherTaskName)
            throws TransitionException, ComponentException {
        log.debug("testing 2 parallel tasks");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 2);
        taskInstanceIterator = processInstance.getTaskInstances().iterator();

        //for (Iterator taskInstanceIterator = processInstance.getTaskInstances().iterator(); taskInstanceIterator.hasNext();) {
        //AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator.next();

        //}

        AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        AntelopeTaskInstance task2 = (AntelopeTaskInstance) taskInstanceIterator
                .next();

        assertNotNull(task);
        assertNotNull(task2);
        boolean taskNameTask = true;//this is whether taskName is the same as task 

        //if this is  

        if (((AntelopeTaskDefinition) task.getTaskDefinition()).getName()
                .equals(otherTaskName)) {
            taskNameTask = false;
            assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition())
                    .getName(), otherTaskName);
            assertEquals(((AntelopeTaskDefinition) task2.getTaskDefinition())
                    .getName(), taskName);
        } else {
            assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition())
                    .getName(), taskName);
            assertEquals(((AntelopeTaskDefinition) task2.getTaskDefinition())
                    .getName(), otherTaskName);
        }

        if (taskName.equals(ARE_THEY_A_PENSIONER)) {
            if (taskNameTask) {
                task.setRoutingAnswer(SHALL_WE_DO_IT_AGAIN);
            } else {
                task2.setRoutingAnswer(SHALL_WE_DO_IT_AGAIN);
            }
        }

        zebraHelper.getEngine().transitionTask(task);

        //taskInstanceIterator = processInstance.getTaskInstances().iterator();
        zebraHelper.getEngine().transitionTask(task2);
    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testTripleTaskDef(String taskName, String otherTaskName,
            String thirdTaskName) throws TransitionException,
            ComponentException {
        log.debug("testing 3 parallel tasks");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 3);
        taskInstanceIterator = processInstance.getTaskInstances().iterator();

        //for (Iterator taskInstanceIterator = processInstance.getTaskInstances().iterator(); taskInstanceIterator.hasNext();) {
        //AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator.next();

        //}

        AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        AntelopeTaskInstance task2 = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        AntelopeTaskInstance task3 = (AntelopeTaskInstance) taskInstanceIterator
                .next();

        assertNotNull(task);
        assertNotNull(task2);
        assertNotNull(task3);
        
        //here comes nasty nested if statement

        if (((AntelopeTaskDefinition) task.getTaskDefinition()).getName()
                .equals(taskName)) {//if task==taskname

            if (((AntelopeTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(otherTaskName)) {//if task2==othertaskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), taskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), otherTaskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), thirdTaskName);
            } else {//																					// task2==thirdtaskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), taskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), thirdTaskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), otherTaskName);
            }
        } else if (((AntelopeTaskDefinition) task.getTaskDefinition())
                .getName().equals(otherTaskName)) {//if task==othertaskname

            if (((AntelopeTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(taskName)) {//if task2==taskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), otherTaskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), taskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), thirdTaskName);
            } else {//																					//task2==thirdtaskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), otherTaskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), thirdTaskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), taskName);
            }
        } else {//																							// task==thirdtaskname

            if (((AntelopeTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(taskName)) {//if task2==taskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), thirdTaskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), taskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), otherTaskName);
            } else {//																					// task2==thirdtaskname
                assertEquals(
                        ((AntelopeTaskDefinition) task.getTaskDefinition())
                                .getName(), thirdTaskName);
                assertEquals(((AntelopeTaskDefinition) task2
                        .getTaskDefinition()).getName(), otherTaskName);
                assertEquals(((AntelopeTaskDefinition) task3
                        .getTaskDefinition()).getName(), taskName);
            }
        }

        //no transitions
        //zebraHelper.getEngine().transitionTask(task);
        //zebraHelper.getEngine().transitionTask(task2);
        //zebraHelper.getEngine().transitionTask(task3);
    }
}

