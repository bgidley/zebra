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

import java.util.Calendar;
import java.util.Date;
import java.util.Iterator;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Ben.Gidley
 */
public class TurbineAntelopeStateFactoryTest extends TurbineTestCase {

    private IStateFactory stateFactory;

    private IAvalonDefsFactory definitionsFactory;

    
    protected void setUp() throws Exception {
    	TurbineAntelopeStateFactoryTest.initialiseTurbine();
        stateFactory = ZebraHelper.getInstance().getStateFactory();
        definitionsFactory = ZebraHelper.getInstance().getDefinitionFactory();
    }

    public void testCreatingTransaction() throws StateFailureException {
        ITransaction transaction = stateFactory.beginTransaction();
        assertNotNull(transaction);

        transaction.commit();

    }

    public void testLoadSaveObjects() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        ITransaction t = stateFactory.beginTransaction();
        IProcessInstance processInstance = stateFactory
                .createProcessInstance(processDefinition);

        
        stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = stateFactory.createFOE(processInstance);
        t = stateFactory.beginTransaction();
        ITaskInstance taskInstance = stateFactory.createTaskInstance(
                taskDefinition, processInstance, foe);        
        stateFactory.saveObject(processInstance);
        stateFactory.saveObject(taskInstance);
        t.commit();

        t = stateFactory.beginTransaction();
        stateFactory.deleteObject(taskInstance);
        t.commit();

        assertFalse(processInstance.getTaskInstances().contains(taskInstance));

        t = stateFactory.beginTransaction();
        stateFactory.deleteObject(processInstance);
        t.commit();

    }

    /**
     * @return
     */
    private IProcessDefinition getProcessDefinition() {
        //Load the first process definition it has (e.g. we don't care which process) 
        Iterator processDefinitions = definitionsFactory
                .getAllProcessDefinitions().keySet().iterator();
        IProcessDefinition processDefinition = (IProcessDefinition) definitionsFactory
                .getAllProcessDefinitions().get(processDefinitions.next());
        return processDefinition;
    }

    public void testCreatingFOE() throws Exception {
        IFOE foe = stateFactory.createFOE(new AntelopeProcessInstance());
        assertNotNull(foe);

    }

    public void testCreateProcessInstance() throws CreateObjectException, DefinitionNotFoundException {
        AntelopeProcessDefinition processDefinition = (AntelopeProcessDefinition) getProcessDefinition();
        AntelopeProcessInstance processInstance = (AntelopeProcessInstance) stateFactory
                .createProcessInstance(processDefinition);
        
        assertEquals(processInstance.getProcessDef(), processDefinition);
        assertEquals(processInstance.getProcessName(), processDefinition.getName());
    }

    public void testCreatingTaskInstance() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = stateFactory
                .createProcessInstance(processDefinition);

        ITransaction t = stateFactory.beginTransaction();
        stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = stateFactory.createFOE(processInstance);
        ITaskInstance taskInstance = stateFactory.createTaskInstance(
                taskDefinition, processInstance, foe);
        assertNotNull(taskInstance);
        assertEquals(processInstance, taskInstance.getProcessInstance());
        assertEquals(foe, taskInstance.getFOE());

        t = stateFactory.beginTransaction();
        stateFactory.saveObject(taskInstance);
        t.commit();

        assertTrue(taskInstance.getTaskInstanceId().longValue() > 0);
    }

    /**
     * Returns the Zebra Component Config location
     */
    protected String getConfigurationFileName() {
        return "src/test/ZebraComponentConfiguration.xml";

    }

    /**
     * Not using a RoleFile so does nothing
     */
    protected String getRoleFileName() {

        return null;
    }

    /**
     * Test the locking
     */
    public void testSimpleLock() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = stateFactory
                .createProcessInstance(processDefinition);
        stateFactory.saveObject(processInstance);

        Date before = Calendar.getInstance().getTime();
        stateFactory.acquireLock(processInstance);
        assertTrue(before.getTime() + 20000 > Calendar.getInstance().getTime()
                .getTime());

        stateFactory.releaseLock(processInstance);

        before = Calendar.getInstance().getTime();
        stateFactory.acquireLock(processInstance);
        assertTrue(before.getTime() + 20000 > Calendar.getInstance().getTime()
                .getTime());

        stateFactory.releaseLock(processInstance);
    }

    public void testThreadedLock() throws Exception {
        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = stateFactory
                .createProcessInstance(processDefinition);
        stateFactory.saveObject(processInstance);

        Locker one = new Locker(processInstance, stateFactory);
        Locker two = new Locker(processInstance, stateFactory);

        Thread runner1 = new Thread(one, "One");
        Thread runner2 = new Thread(two, "Two");

        // Runner 1 will start and aquire lock
        runner1.start();
        Thread.sleep(1000);
        assertTrue(one.locked);
        // Runner 2 should start an wait on 1
        runner2.start();
        assertFalse(two.locked);
        one.wait = false;
        Thread.sleep(1000);
        assertTrue(one.unlocked);
        assertFalse(one.locked);
        assertTrue(two.locked);
        two.wait = false;
        Thread.sleep(1000);
        assertTrue(two.unlocked);
        assertFalse(two.locked);
    }

    /**
     * Workflow Runner
     */
    private static class Locker implements Runnable {

        public boolean locked = false;

        public boolean unlocked = false;

        public boolean wait = true;

        public IStateFactory stateFactory;

        IProcessInstance instance;

        public Locker(IProcessInstance instance, IStateFactory stateFactory) {
            this.instance = instance;
            this.stateFactory = stateFactory;
        }

        public void run() {
            try {
                stateFactory.acquireLock(instance);
                locked = true;
                while (wait) {
                    Thread.sleep(1);
                }

                stateFactory.releaseLock(instance);
                locked = false;
                unlocked = true;
            } catch (LockException e) {
                assertNull(e);

            } catch (InterruptedException e) {
                assertNull(e);
            }

        }

    }

}