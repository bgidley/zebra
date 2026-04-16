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

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;
import org.hibernate.Session;

import com.anite.zebra.core.state.api.ITransaction;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraPropertySetEntry;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.taskAction.NoopActivity1;

public class PropertySetBehaviourTest extends TestCase {
    private static final String BOB = "Bob";

    private Zebra zebra;

    private Session session;

    protected void setUp() throws Exception {
        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);

        this.zebra = (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra", Zebra.class);
        this.session = (Session) RegistryManager.getInstance().getRegistry().getService(Session.class);
    }

//    public void testManualWorkflow() throws Exception {
//        ZebraProcessInstance pi = zebra.createProcessPaused("TestPropertySetPersistence");
//
//        zebra.startProcess(pi);
//        // Should go to activity 1
//
//        int i = 0;
//        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
//            i++;
//            zebra.transitionTask(instance);
//        }
//        assertEquals(1, NoopActivity1.executionCount);
//        assertEquals(1, i);
//
//        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
//            i++;
//            zebra.transitionTask(instance);
//        }
//        assertEquals(2, NoopActivity1.executionCount);
//        assertEquals(2, i);
//
//        // Quartz task should wait 1 seconds        
//        Thread.sleep(2000);
//
//        // As this happend on another thread the test must load it from the db again.
//        session.evict(pi);
//        pi = (ZebraProcessInstance) session.load(ZebraProcessInstance.class, pi.getProcessInstanceId());
//
//        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
//            i++;
//            zebra.transitionTask(instance);
//        }
//        assertEquals(3, NoopActivity1.executionCount);
//        assertEquals(3, i);
//    }

    public void testPropertySet() throws Exception {

        ZebraProcessInstance pi = zebra.createProcessPaused("TestPropertySetPersistence");

        ZebraPropertySetEntry entry = new ZebraPropertySetEntry(BOB);
        pi.getPropertySet().put(BOB, entry);
        entry.setProcessInstance(pi);
        entry.setKey(BOB);
        
        zebra.startProcess(pi);

        NoopActivity1.executionCount = 0;
        
        int i = 0;
        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
            i++;
            zebra.transitionTask(instance);
        }
        assertEquals(1, NoopActivity1.executionCount);
        assertEquals(1, i);

        session.evict(pi);
        RegistryManager.getInstance().getRegistry().cleanupThread();
        pi = (ZebraProcessInstance) session.load(ZebraProcessInstance.class, pi.getProcessInstanceId());
        
        ZebraPropertySetEntry bobEntry = pi.getPropertySet().get(BOB);
        assertNotNull(bobEntry);
        assertEquals(BOB, bobEntry.getValue());
        
        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
            i++;
            ZebraPropertySetEntry entry2 = new ZebraPropertySetEntry(BOB);
            instance.getPropertySet().put(BOB, entry2);
            entry2.setTaskInstance(instance);
            entry2.setKey(BOB);
            
            ITransaction t = zebra.getStateFactory().beginTransaction();
            zebra.getStateFactory().saveObject(instance);
            t.commit();
            
            session.evict(instance);
            RegistryManager.getInstance().getRegistry().cleanupThread();
            instance = (ZebraTaskInstance) session.load(ZebraTaskInstance.class, instance.getTaskInstanceId());
            ZebraPropertySetEntry bobEntry2 = instance.getPropertySet().get(BOB);
            assertNotNull(bobEntry2);
            assertEquals(BOB, bobEntry2.getValue());
            
        }
        
    }
    
    public void testPropertySetHelpers() throws Exception {

        ZebraProcessInstance pi = zebra.createProcessPaused("TestPropertySetPersistence");

        ZebraPropertySetEntry entry = new ZebraPropertySetEntry(BOB);
        pi.addPropertySetEntry(BOB, entry);
        
        zebra.startProcess(pi);

        NoopActivity1.executionCount = 0;
        
        int i = 0;
        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
            i++;
            zebra.transitionTask(instance);
        }
        assertEquals(1, NoopActivity1.executionCount);
        assertEquals(1, i);

        session.evict(pi);
        RegistryManager.getInstance().getRegistry().cleanupThread();
        pi = (ZebraProcessInstance) session.load(ZebraProcessInstance.class, pi.getProcessInstanceId());
        
        ZebraPropertySetEntry bobEntry = pi.getPropertySet().get(BOB);
        assertNotNull(bobEntry);
        assertEquals(BOB, bobEntry.getValue());
        
        for (ZebraTaskInstance instance : pi.getTaskInstances()) {
            i++;
            ZebraPropertySetEntry entry2 = new ZebraPropertySetEntry(BOB);
            instance.addPropertySetEntry(BOB, entry2);
            
            
            ITransaction t = zebra.getStateFactory().beginTransaction();
            zebra.getStateFactory().saveObject(instance);
            t.commit();
            
            session.evict(instance);
            RegistryManager.getInstance().getRegistry().cleanupThread();
            instance = (ZebraTaskInstance) session.load(ZebraTaskInstance.class, instance.getTaskInstanceId());
            ZebraPropertySetEntry bobEntry2 = instance.getPropertySet().get(BOB);
            assertNotNull(bobEntry2);
            assertEquals(BOB, bobEntry2.getValue());
            
        }
        
        // Remove something from the process property set
        RegistryManager.getInstance().getRegistry().cleanupThread();
        pi = (ZebraProcessInstance) session.load(ZebraProcessInstance.class, pi.getProcessInstanceId());
        pi.removePropertySetEntry(BOB);
        
        ITransaction t = zebra.getStateFactory().beginTransaction();
        zebra.getStateFactory().saveObject(pi);
        t.commit();
        
        session.evict(pi);
        RegistryManager.getInstance().getRegistry().cleanupThread();
        pi = (ZebraProcessInstance) session.load(ZebraProcessInstance.class, pi.getProcessInstanceId());
       
        assertFalse(pi.getPropertySet().containsKey(BOB));
        
        
    }
}
