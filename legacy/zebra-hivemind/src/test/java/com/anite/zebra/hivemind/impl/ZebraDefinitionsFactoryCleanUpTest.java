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

import java.util.Iterator;
import java.util.Set;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;

public class ZebraDefinitionsFactoryCleanUpTest extends TestCase {
    private static final String WELCOME_TO_WORKFLOW = "Welcome to workflow";

    private static final String SIMPLEWORKFLOW = "SimpleWorkflow";

    private ZebraDefinitionFactory zebraDefinitionFactory;

    protected void setUp() throws Exception {

        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);

        this.zebraDefinitionFactory = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);
    }

    /**
     * As we cache definitions we can get session issues when we change threads
     * or cleanup the registry. This test simulates that behaviour.
     * @throws DefinitionNotFoundException 
     *
     */
    public void testGetTaskDefinitionFromCache() {

        ZebraProcessDefinition processDefinition = this.zebraDefinitionFactory
                .getProcessDefinitionByName(SIMPLEWORKFLOW);
        assertNotNull(processDefinition);
        assertEquals(SIMPLEWORKFLOW, processDefinition.getName());

        assertTrue(processDefinition.getTaskDefinitions().size() == 5);
        // find a task
        TaskDefinition task = (TaskDefinition) processDefinition.getFirstTask();
        // discover task name (we are using the Welcome to workflow one)
        assertEquals(WELCOME_TO_WORKFLOW, task.getName());

        Long taskId = task.getId();
        // Now we have loaded the task up (as normal) clean up the thread 
        RegistryManager.getInstance().getRegistry().cleanupThread();

        TaskDefinition taskDefinition = this.zebraDefinitionFactory.getTaskDefinition(taskId);
        forceLoadOfAllItems(taskDefinition);

    }

    public void forceLoadOfAllItems(TaskDefinition taskDefinition) {
        Set routings = taskDefinition.getRoutingOut();
        for (Iterator iter = routings.iterator(); iter.hasNext();) {
            RoutingDefinition routing = (RoutingDefinition) iter.next();
            assertNotNull(routing.getId());
        }

        IPropertyGroups groups = taskDefinition.getPropertyGroups();
        assertNotNull(groups.toString());

    }
}
