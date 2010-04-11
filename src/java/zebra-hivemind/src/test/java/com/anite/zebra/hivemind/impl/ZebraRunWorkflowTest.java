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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * Run a workflow from End to end
 * @author John Rae
 */
public class ZebraRunWorkflowTest extends TestCase {
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

    private static final String SUBPROCESS_TASK = "SubProcess Task";

    private static final String DO_YOU_WANT_TO_TRY_AND_SUBPROCESS = "Do you want to try and subprocess?";

    private static final String ENTER_SOME_DATA = "Enter some data";

    private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

    private static final String SIMPLE_WORKFLOW = "SimpleWorkflow";

    private static final String SPLIT_WORKFLOW = "Split";

    private static Log log = LogFactory.getLog(ZebraRunWorkflowTest.class);


    private Zebra zebra;
    
    protected void setUp() throws Exception {
        Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);
        
        
        this.zebra = (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra",Zebra.class);
    }

    public void testRunSimpleWorkflow() throws Exception             {

        runSimpleWorkflow(YES);
        runSimpleWorkflow(NO);
    }

    public void testRunSplitWorkflow() throws Exception{

        runSplitWorkflow(YES);
        runSplitWorkflow(NO);
        runSplitWorkflow(SHALL_WE_DO_IT_AGAIN);
    }

  
    private void runSimpleWorkflow(String test) throws Exception  {
        log.debug("testing Simple Workflow");
        
        ZebraProcessInstance processInstance = zebra.createProcessPaused(SIMPLE_WORKFLOW);
        assertNotNull(processInstance);

        zebra.startProcess(processInstance);

        testTaskDef(WELCOME_TO_WORKFLOW, processInstance);

        testTaskDef(ENTER_SOME_DATA, processInstance);

        testTaskDef(DO_YOU_WANT_TO_TRY_AND_SUBPROCESS, test, processInstance);

        if (test == YES) {
            testTaskDef(SUBPROCESS_TASK,
                    (ZebraProcessInstance) processInstance
                            .getRunningChildProcesses().get(0));
        }

        testTaskDef(THE_END, processInstance);

    }

    public void runSplitWorkflow(String test) throws Exception {
        log.debug("testing Split workflow");

        ZebraProcessInstance processInstance = zebra.createProcessPaused(SPLIT_WORKFLOW);
        assertNotNull(processInstance);
        
        zebra.startProcess(processInstance);

        testTaskDef(MANUAL_ACTIVITY, processInstance);

        testTaskDef(ARE_THEY_A_PENSIONER, test,  processInstance);

        if (test == YES) {
            testDualTaskDef(ASK_IF_THEY_ARE_BORED,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY, processInstance);
            testDualTaskDef(SEND_THEM_A_LETTER, SEND_THEM_A_LETTER, processInstance);

        } else if (test == NO) {
            testDualTaskDef(ASK_IF_THEY_HAVE_A_PENSION,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY, processInstance);
            testDualTaskDef(SEND_THEM_A_LETTER, SEND_THEM_A_LETTER, processInstance);

        } else if (test == SHALL_WE_DO_IT_AGAIN) {
            testDualTaskDef(ARE_THEY_A_PENSIONER,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY, processInstance);//just do this once but in reality it would repeat infinitely
            testTripleTaskDef(ARE_THEY_A_PENSIONER,
                    GIVE_THEM_A_CUSTOMER_SATISFACTION_SURVEY,
                    SEND_THEM_A_LETTER, processInstance);

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
            ZebraProcessInstance antelopeProcessInstance) throws Exception
           {
        log.debug("testing task");
        //get process
        //check correct process
        //advance flow
        assertEquals(antelopeProcessInstance.getTaskInstances().size(), 1);
        Iterator<ZebraTaskInstance> taskInstanceIterator = antelopeProcessInstance.getTaskInstances()
                .iterator();
        ZebraTaskInstance task =  taskInstanceIterator
                .next();
        assertNotNull(task);
        assertEquals(((ZebraTaskDefinition) task.getTaskDefinition())
                .getName(), taskName);
        zebra.transitionTask(task);
    }

     /**
     * @param taskName
     * @param test
     * @throws TransitionException
     * @throws DefinitionNotFoundException 
     * @throws ComponentException
     * 
     * tests Task Definitions that take a parameter for routing
     */
    private void testTaskDef(String taskName, String test, ZebraProcessInstance processInstance)
            throws TransitionException, DefinitionNotFoundException {
        log.debug("testing task");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 1);
        Iterator<ZebraTaskInstance> taskInstanceIterator = processInstance.getTaskInstances().iterator();
        ZebraTaskInstance task = taskInstanceIterator
                .next();
        assertNotNull(task);
        assertEquals(((ZebraTaskDefinition) task.getTaskDefinition())
                .getName(), taskName);
        task.setRoutingAnswer(test);
        zebra.transitionTask(task);
    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws DefinitionNotFoundException 
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testDualTaskDef(String taskName, String otherTaskName, ZebraProcessInstance processInstance)
            throws TransitionException, DefinitionNotFoundException  {
        log.debug("testing 2 parallel tasks");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 2);
        Iterator<ZebraTaskInstance> taskInstanceIterator = processInstance.getTaskInstances().iterator();

        ZebraTaskInstance task = taskInstanceIterator
                .next();
        ZebraTaskInstance task2 = taskInstanceIterator
                .next();

        assertNotNull(task);
        assertNotNull(task2);
        boolean taskNameTask = true;//this is whether taskName is the same as task 

        //if this is  

        if (((ZebraTaskDefinition) task.getTaskDefinition()).getName()
                .equals(otherTaskName)) {
            taskNameTask = false;
            assertEquals(((ZebraTaskDefinition) task.getTaskDefinition())
                    .getName(), otherTaskName);
            assertEquals(((ZebraTaskDefinition) task2.getTaskDefinition())
                    .getName(), taskName);
        } else {
            assertEquals(((ZebraTaskDefinition) task.getTaskDefinition())
                    .getName(), taskName);
            assertEquals(((ZebraTaskDefinition) task2.getTaskDefinition())
                    .getName(), otherTaskName);
        }

        if (taskName.equals(ARE_THEY_A_PENSIONER)) {
            if (taskNameTask) {
                task.setRoutingAnswer(SHALL_WE_DO_IT_AGAIN);
            } else {
                task2.setRoutingAnswer(SHALL_WE_DO_IT_AGAIN);
            }
        }

        zebra.transitionTask(task);

        //taskInstanceIterator = processInstance.getTaskInstances().iterator();
        zebra.transitionTask(task2);
    }

    /**
     * @param taskName
     * @throws DefinitionNotFoundException 
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private void testTripleTaskDef(String taskName, String otherTaskName,
            String thirdTaskName, ZebraProcessInstance processInstance) throws DefinitionNotFoundException {
        log.debug("testing 3 parallel tasks");
        //get process
        //check correct process
        //advance flow
        assertEquals(processInstance.getTaskInstances().size(), 3);
        Iterator<ZebraTaskInstance> taskInstanceIterator = processInstance.getTaskInstances().iterator();

        ZebraTaskInstance task = taskInstanceIterator
                .next();
        ZebraTaskInstance task2 = taskInstanceIterator
                .next();
        ZebraTaskInstance task3 = taskInstanceIterator
                .next();

        assertNotNull(task);
        assertNotNull(task2);
        assertNotNull(task3);
        
        //here comes nasty nested if statement

        if (((ZebraTaskDefinition) task.getTaskDefinition()).getName()
                .equals(taskName)) {//if task==taskname

            if (((ZebraTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(otherTaskName)) {//if task2==othertaskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), taskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), otherTaskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), thirdTaskName);
            } else {//																					// task2==thirdtaskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), taskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), thirdTaskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), otherTaskName);
            }
        } else if (((ZebraTaskDefinition) task.getTaskDefinition())
                .getName().equals(otherTaskName)) {//if task==othertaskname

            if (((ZebraTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(taskName)) {//if task2==taskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), otherTaskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), taskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), thirdTaskName);
            } else {//																					//task2==thirdtaskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), otherTaskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), thirdTaskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), taskName);
            }
        } else {//																							// task==thirdtaskname

            if (((ZebraTaskDefinition) task2.getTaskDefinition()).getName()
                    .equals(taskName)) {//if task2==taskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), thirdTaskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), taskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), otherTaskName);
            } else {//																					// task2==thirdtaskname
                assertEquals(
                        ((ZebraTaskDefinition) task.getTaskDefinition())
                                .getName(), thirdTaskName);
                assertEquals(((ZebraTaskDefinition) task2
                        .getTaskDefinition()).getName(), otherTaskName);
                assertEquals(((ZebraTaskDefinition) task3
                        .getTaskDefinition()).getName(), taskName);
            }
        }

    }
}

