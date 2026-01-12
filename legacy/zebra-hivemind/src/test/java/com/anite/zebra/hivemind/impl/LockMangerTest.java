/*
 * Copyright 2004, 2005 Anite 
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

import java.util.Calendar;
import java.util.Date;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITransaction;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;

public class LockMangerTest extends TestCase {
	private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

    public void setUp() {

        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);

        this.stateFactory = (IStateFactory) RegistryManager.getInstance().getRegistry().getService("zebra.zebraState",
                IStateFactory.class);
        this.definitionsFactory = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);
    }

    private IStateFactory stateFactory;

    private ZebraDefinitionFactory definitionsFactory;

    /**
     * @return
     */
    private ZebraProcessDefinition getProcessDefinition() {
        // Load the first process definition it has (e.g. we don't care which
        // process)
        return this.definitionsFactory.getProcessDefinitionByName(SIMPLEWORKFLOW);
    }

    /**
     * Test the locking
     */
    public void testSimpleLock() throws Exception {

        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = this.stateFactory.createProcessInstance(processDefinition);
        ITransaction transaction = this.stateFactory.beginTransaction();
        this.stateFactory.saveObject(processInstance);
        transaction.commit();

        Date before = Calendar.getInstance().getTime();
        this.stateFactory.acquireLock(processInstance, null);
        assertTrue(before.getTime() + 20000 > Calendar.getInstance().getTime().getTime());

        this.stateFactory.releaseLock(processInstance, null);

        before = Calendar.getInstance().getTime();
        this.stateFactory.acquireLock(processInstance, null);
        assertTrue(before.getTime() + 20000 > Calendar.getInstance().getTime().getTime());

        this.stateFactory.releaseLock(processInstance, null);
    }

    public void testThreadedLock() throws Exception {
        IProcessDefinition processDefinition = getProcessDefinition();

        IProcessInstance processInstance = this.stateFactory.createProcessInstance(processDefinition);
        this.stateFactory.saveObject(processInstance);

        Locker one = new Locker(processInstance, this.stateFactory);
        Locker two = new Locker(processInstance, this.stateFactory);

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
                this.stateFactory.acquireLock(this.instance, null);
                this.locked = true;
                while (this.wait) {
                    Thread.sleep(1);
                }

                this.stateFactory.releaseLock(this.instance, null);
                this.locked = false;
                this.unlocked = true;
            } catch (LockException e) {
                assertNull(e);

            } catch (InterruptedException e) {
                assertNull(e);
            }

        }

    }

}
