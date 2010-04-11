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

import junit.framework.TestCase;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author Eric.pugh
 */
public class XMLLoadProcessTest extends TestCase {

    private Class processDefClass;
    private Class taskDefClass;
    private Class processVersionsClass;
    private Class propertyElementClass;
    private Class propertyGroupsClass;
    private Class routingDefinitionClass;

    private File xmlFile;

    public void setUp() throws Exception {
        processDefClass = Class.forName("com.anite.zebra.ext.definitions.impl.ProcessDefinition");
        taskDefClass = Class.forName("com.anite.zebra.ext.definitions.impl.TaskDefinition");
        processVersionsClass = Class.forName("com.anite.zebra.ext.definitions.impl.ProcessVersions");
        propertyElementClass = Class.forName("com.anite.zebra.ext.definitions.impl.PropertyElement");
        propertyGroupsClass = Class.forName("com.anite.zebra.ext.definitions.impl.PropertyGroups");
        routingDefinitionClass = Class.forName("com.anite.zebra.ext.definitions.impl.RoutingDefinition");
        
    }

    public void testExceptionThrownWhenMissingProperties() {
        try {
            XMLLoadProcess loadProcess = new XMLLoadProcess();
            loadProcess.checkProperties();
            fail("Should have thrown exception");
        } catch (Exception e) {
            //good
        }
    }

    public void testLoadNoWhiteSpaceInXML() throws Exception {

        XMLLoadProcess loadProcess = new XMLLoadProcess();
        loadProcess.setProcessDefinitionClass(processDefClass);
        loadProcess.setTaskDefinitionClass(taskDefClass);
        loadProcess.setProcessVersionsClass(processVersionsClass);
        loadProcess.setPropertyElementClass(propertyElementClass);
        loadProcess.setPropertyGroupsClass(propertyGroupsClass);
        loadProcess.setRoutingDefinitionClass(routingDefinitionClass);
        xmlFile = new File("src/test/resources/test-resources/nowhitespace.acgwfd.xml");
        IProcessVersions results = loadProcess.loadFromFile(xmlFile);
        assertEquals(3, results.getProcessVersions().size());
    }

    public void testLoadPrettyPrintedXML() throws Exception {

        XMLLoadProcess loadProcess = new XMLLoadProcess();
        loadProcess.setProcessDefinitionClass(processDefClass);
        loadProcess.setTaskDefinitionClass(taskDefClass);
        loadProcess.setProcessVersionsClass(processVersionsClass);
        loadProcess.setPropertyElementClass(propertyElementClass);
        loadProcess.setPropertyGroupsClass(propertyGroupsClass);
        loadProcess.setRoutingDefinitionClass(routingDefinitionClass);
        File xmlFile = new File("src/test/resources/test-resources/prettyprinted.acgwfd.xml");

        IProcessVersions results = loadProcess.loadFromFile(xmlFile);
        assertEquals("New Test1 Process",results.getName());
        assertEquals(3, results.getProcessVersions().size());
        IProcessVersion latestVersion = results.getLatestProcessVersion();
        assertEquals(4,latestVersion.getVersion().longValue());
        IProcessDefinition ipd = (IProcessDefinition)latestVersion;
        ProcessDefinition pd = (ProcessDefinition)ipd;
        IProperties properties = pd.getPropertyGroups().getProperties("Visibility");
        assertTrue(properties.getBoolean("DebugFlow"));
        assertTrue(properties.containsKey("DebugFlow"));
        TaskDefinition td3 = (TaskDefinition)pd.getTaskDefs().getTaskDef(new Long(3));
        assertEquals("DefaultDecision.vm",td3.getPropertyGroups().getProperties("Screen").getString("Screen Name"));
        assertTrue(td3.getPropertyGroups().getProperties("Screen").getBoolean("Auto Show"));
    }
    
    public void testLoadOneBadOneGoodXML() throws Exception{
    	XMLLoadProcess loadProcess = new XMLLoadProcess();
        loadProcess.setProcessDefinitionClass(processDefClass);
        loadProcess.setTaskDefinitionClass(taskDefClass);
        loadProcess.setProcessVersionsClass(processVersionsClass);
        loadProcess.setPropertyElementClass(propertyElementClass);
        loadProcess.setPropertyGroupsClass(propertyGroupsClass);
        loadProcess.setRoutingDefinitionClass(routingDefinitionClass);
        File xmlFile = new File("src/test/resources/test-resources/OneBadOneGoodVersion.acgwfd.xml");
        
        IProcessVersions results = loadProcess.loadFromFile(xmlFile);
        assertEquals(results.getProcessVersions().size(),1);
    }
    
    public void testLoadOneBad() throws Exception{
    	XMLLoadProcess loadProcess = new XMLLoadProcess();
        loadProcess.setProcessDefinitionClass(processDefClass);
        loadProcess.setTaskDefinitionClass(taskDefClass);
        loadProcess.setProcessVersionsClass(processVersionsClass);
        loadProcess.setPropertyElementClass(propertyElementClass);
        loadProcess.setPropertyGroupsClass(propertyGroupsClass);
        loadProcess.setRoutingDefinitionClass(routingDefinitionClass);
        File xmlFile = new File("src/test/resources/test-resources/OneBad.acgwfd.xml");
        
        IProcessVersions results = loadProcess.loadFromFile(xmlFile);
        assertEquals(results.getProcessVersions().size(),0);
    }
}