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

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;
import com.anite.zebra.hivemind.api.StateFactoryEvent;
import com.anite.zebra.hivemind.api.StateFactoryListener;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.api.ZebraStateFactory;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraPropertySetEntry;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * @author Ben.Gidley
 */
public class ZebraStateFactoryTest extends TestCase {
    public class InnerStateListener implements StateFactoryListener {
        public int count = 0;

        public void createTaskInstance(StateFactoryEvent stateFactoryEvent) {
            count++;

        }

    }

    private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

    private ZebraStateFactory stateFactory;

    private ZebraDefinitionFactory definitionsFactory;

    protected void setUp() throws Exception {

        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);

        this.stateFactory = (ZebraStateFactory) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraState", ZebraStateFactory.class);
        this.definitionsFactory = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);

    }

    public void testCreatingTransaction() throws StateFailureException {
        ITransaction transaction = this.stateFactory.beginTransaction();
        assertNotNull(transaction);

        transaction.commit();

    }

    public void testLoadSaveObjects() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        ITransaction t = this.stateFactory.beginTransaction();
        ZebraProcessInstance processInstance = (ZebraProcessInstance) this.stateFactory
                .createProcessInstance(processDefinition);
        ZebraPropertySetEntry propSet = new ZebraPropertySetEntry();
        propSet.setValue("temp");
        processInstance.getPropertySet().put("One", propSet);
        this.stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = this.stateFactory.createFOE(processInstance);
        t = this.stateFactory.beginTransaction();
        ZebraTaskInstance taskInstance = (ZebraTaskInstance) this.stateFactory.createTaskInstance(taskDefinition,
                processInstance, foe);
        ZebraPropertySetEntry propSet2 = new ZebraPropertySetEntry();
        propSet2.setValue("temp");
        processInstance.getPropertySet().put("One", propSet2);

        this.stateFactory.saveObject(processInstance);
        this.stateFactory.saveObject(taskInstance);
        t.commit();

        t = this.stateFactory.beginTransaction();
        this.stateFactory.deleteObject(taskInstance);
        t.commit();

        assertFalse(processInstance.getTaskInstances().contains(taskInstance));

        t = this.stateFactory.beginTransaction();
        this.stateFactory.deleteObject(processInstance);
        try {
            t.commit();
        } catch (StateFailureException te) {
            fail();
        }

    }

    /**
     * @return
     */
    private ZebraProcessDefinition getProcessDefinition() {
        // Load the first process definition it has (e.g. we don't care which
        // process)
        return this.definitionsFactory.getProcessDefinitionByName(SIMPLEWORKFLOW);
    }

    public void testCreatingFOE() throws Exception {
        IFOE foe = this.stateFactory.createFOE(new ZebraProcessInstance());
        assertNotNull(foe);

    }

    public void testCreateProcessInstance() throws CreateObjectException, DefinitionNotFoundException {
        ZebraProcessDefinition processDefinition = getProcessDefinition();
        ZebraProcessInstance processInstance = (ZebraProcessInstance) this.stateFactory
                .createProcessInstance(processDefinition);

        assertEquals(processInstance.getProcessDef(), processDefinition);
        assertEquals(processInstance.getProcessName(), processDefinition.getName());
    }

    public void testCreatingTaskInstance() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = this.stateFactory.createProcessInstance(processDefinition);

        ITransaction t = this.stateFactory.beginTransaction();
        this.stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = this.stateFactory.createFOE(processInstance);
        ITaskInstance taskInstance = this.stateFactory.createTaskInstance(taskDefinition, processInstance, foe);
        assertNotNull(taskInstance);
        assertEquals(processInstance, taskInstance.getProcessInstance());
        ZebraTaskInstance zebraTaskInstance = (ZebraTaskInstance) taskInstance;
        zebraTaskInstance.getPropertySet().put("bob", new ZebraPropertySetEntry("bob"));
        assertEquals(foe, taskInstance.getFOE());

        t = this.stateFactory.beginTransaction();
        this.stateFactory.saveObject(taskInstance);
        t.commit();

        assertTrue(taskInstance.getTaskInstanceId().longValue() > 0);

        t = this.stateFactory.beginTransaction();
        this.stateFactory.deleteObject(taskInstance);
        t.commit();

    }

    /**
     * Add a listener via a eager loaded service
     * @throws Exception
     */
    public void testServiceEventFiring() throws Exception {

        StateFactoryListener stateFactoryListener = (StateFactoryListener) RegistryManager.getInstance().getRegistry()
                .getService(StateFactoryListener.class);
        stateFactoryListener.createTaskInstance(null);

        int count = StateFactoryListenerService.count;

        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = this.stateFactory.createProcessInstance(processDefinition);

        ITransaction t = this.stateFactory.beginTransaction();
        this.stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = this.stateFactory.createFOE(processInstance);
        ITaskInstance taskInstance = this.stateFactory.createTaskInstance(taskDefinition, processInstance, foe);
        assertNotNull(taskInstance);

        assertEquals(count + 1, StateFactoryListenerService.count);

    }

    /**
     * Add a listener directly to the service
     * @throws Exception
     */
    public void testNonServiceEventFiring() throws Exception {
        StateFactoryListener listener = new InnerStateListener();

        stateFactory.addStateFactoryListener(listener);

        int count = ((InnerStateListener) listener).count;

        IProcessDefinition processDefinition = getProcessDefinition();
        IProcessInstance processInstance = this.stateFactory.createProcessInstance(processDefinition);

        ITransaction t = this.stateFactory.beginTransaction();
        this.stateFactory.saveObject(processInstance);
        t.commit();

        ITaskDefinition taskDefinition = processDefinition.getFirstTask();

        IFOE foe = this.stateFactory.createFOE(processInstance);
        ITaskInstance taskInstance = this.stateFactory.createTaskInstance(taskDefinition, processInstance, foe);
        assertNotNull(taskInstance);

        assertEquals(count + 1, ((InnerStateListener) listener).count);

    }

}