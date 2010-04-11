/*
 * Copyright 2004/2005 Anite - Enforcement & Security
 * http://www.anite.com/publicsector
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 * 
 * http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */

package com.anite.zebra.ext.xmlloader;

import java.io.File;
import java.util.Iterator;

import junit.framework.TestCase;

import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.IRoutingDefinitions;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinitions;
import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;
import com.anite.zebra.ext.definitions.impl.ProcessVersions;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author Eric.pugh
 */
public class SimpleTest extends TestCase {
    private Class processDefClass;

    private Class taskDefClass;

    private Class processVersionsClass;

    private Class propertyElementClass;

    private Class propertyGroupsClass;

    private Class routingDefinitionClass;

    public void setUp() throws Exception {
        processDefClass = Class.forName("com.anite.zebra.ext.definitions.impl.ProcessDefinition");
        taskDefClass = Class.forName("com.anite.zebra.ext.definitions.impl.TaskDefinition");
        processVersionsClass = Class.forName("com.anite.zebra.ext.definitions.impl.ProcessVersions");
        propertyElementClass = Class.forName("com.anite.zebra.ext.definitions.impl.PropertyElement");
        propertyGroupsClass = Class.forName("com.anite.zebra.ext.definitions.impl.PropertyGroups");
        routingDefinitionClass = Class.forName("com.anite.zebra.ext.definitions.impl.RoutingDefinition");

    }

    public void testLoadingObjectsLoadedFromXML() throws Exception {
        LoadFromFile lf = new LoadFromFile();
        lf.setProcessDefinitionClass(processDefClass);
        lf.setTaskDefinitionClass(taskDefClass);
        lf.setProcessVersionsClass(processVersionsClass);
        lf.setPropertyElementClass(propertyElementClass);
        lf.setPropertyGroupsClass(propertyGroupsClass);
        lf.setRoutingDefinitionClass(routingDefinitionClass);
        lf.loadProcessDef(new File("src/test/resources/test-resources/testLoadingObjectsLoadedFromXML.acgwfd.xml")
                .getAbsoluteFile());

        assertEquals("Loaded " + lf.getAllProcessVersions().size() + " process versions", 1, lf.getAllProcessVersions()
                .size());

        assertEquals(1, lf.getAllProcessVersions().size());
        Iterator it = lf.getAllProcessVersions().iterator();
        ProcessVersions pv = (ProcessVersions) it.next();
        ProcessDefinition apd = (ProcessDefinition) pv.getLatestProcessVersion();
        assertEquals(1, apd.getVersion().longValue());
        assertEquals("New Test1 Process", apd.getName());
        assertNull(apd.getClassConstruct());
        assertNull(apd.getClassDestruct());
        IPropertyGroups propertyGroups = apd.getPropertyGroups();
        assertNotNull(propertyGroups.getProperties("CTMS"));
        assertNotNull(propertyGroups.getProperties("FakeGroup"));

        IProperties ctmsProperties = propertyGroups.getProperties("CTMS");
        String s = (String) ctmsProperties.get("Display Name");
        assertEquals("Add Note", s);
        assertSame(s, ctmsProperties.getString("Display Name"));

        ITaskDefinitions taskDefs = apd.getTaskDefs();

        ITaskDefinition taskDef = taskDefs.getTaskDef(new Long(1));
        assertNotNull(taskDef);
        Long id = taskDef.getId();
        assertEquals(1, id.longValue());
        TaskDefinition atd = (TaskDefinition) taskDef;
        IPropertyGroups atdPropertyGroups = atd.getPropertyGroups();
        IProperties atdProperties = atdPropertyGroups.getProperties("Test1 Properties");
        assertEquals("Test1 Properties", atdProperties.getName());
        assertNull(atdProperties.getString("Another Property"));
        assertEquals("2", atdProperties.getString("Another Property2"));

        IRoutingDefinitions routingDefs = apd.getRoutingDefs();
        Iterator i = routingDefs.iterator();
        IRoutingDefinition routingDef = (IRoutingDefinition) i.next();
        assertFalse(i.hasNext());
        assertEquals(3, routingDef.getId().longValue());
        assertEquals(1, routingDef.getOriginatingTaskDefinition().getId().longValue());
        assertEquals(2, routingDef.getDestinationTaskDefinition().getId().longValue());

    }
}