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

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * @author Ben.Gidley
 */
public class TurbineZebraHelperTest extends TestCase {

    private static final String SIMPLE_WORKFLOW = "SimpleWorkflow";

    private static Log log = LogFactory.getLog(TurbineZebraHelperTest.class);

    private ZebraHelper zebraHelper;

    protected void setUp() throws Exception {
        zebraHelper = ZebraHelper.getInstance();

       TurbineTestCase.initialiseTurbine();
    }

    public void testGetProcessDefinition() throws NestableException {
        AntelopeProcessDefinition processDefinition = zebraHelper
                .getProcessDefinition(SIMPLE_WORKFLOW);
        assertNotNull(processDefinition);
    }

    /*
     * Class under test for AntelopeProcessInstance createProcessPaused(String)
     */
    public void testCreateProcessPausedString() throws NestableException {
        AntelopeProcessInstance processInstance = zebraHelper
                .createProcessPaused(SIMPLE_WORKFLOW);
        assertNotNull(processInstance);

    }

    public void testGetTaskInstance() throws NestableException,
            StartProcessException, ComponentException {

        AntelopeProcessInstance processInstance = zebraHelper
                .createProcessPaused(SIMPLE_WORKFLOW);
        assertNotNull(processInstance);

        zebraHelper.getEngine().startProcess(processInstance);
        Iterator taskInstanceIterator = processInstance.getTaskInstances()
                .iterator();
        // There should be only 1 task (Welcome to Workflow)
        AntelopeTaskInstance taskInstance = (AntelopeTaskInstance) taskInstanceIterator
                .next();

        assertNotNull(taskInstance);
        Long taskInstanceId = taskInstance.getTaskInstanceId();

        AntelopeTaskInstance zebraFetchTaskInstace = zebraHelper
                .getTaskInstance(taskInstanceId);
        assertEquals(taskInstance, zebraFetchTaskInstace);
    }

    /*
     * Class under test for AntelopeProcessInstance createProcessPaused(AntelopeProcessDefinition)
     */
    public void testCreateProcessPausedAntelopeProcessDefinition()
            throws NestableException {
        AntelopeProcessInstance processInstance = zebraHelper
                .createProcessPaused(SIMPLE_WORKFLOW);
        assertNotNull(processInstance);
        assertEquals(processInstance.getState(), IProcessInstance.STATE_CREATED);
    }

    public void testGetEngine() throws ComponentException {
        IEngine engine = zebraHelper.getEngine();
        assertNotNull(engine);
    }

    public void testGetDefinitionFactory() throws ComponentException {
        IAvalonDefsFactory defsFactory = zebraHelper.getDefinitionFactory();
        assertNotNull(defsFactory);
    }

    public void testGetStateFactory() throws ComponentException {
        IStateFactory stateFactory = zebraHelper.getStateFactory();
        assertNotNull(stateFactory);
    }

}