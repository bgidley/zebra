/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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
package com.anite.zebra.ext.definitions.impl;

import java.util.HashSet;
import java.util.Set;

import com.anite.zebra.core.definitions.api.IRoutingDefinitions;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinitions;
import com.anite.zebra.ext.definitions.api.AbstractProcessDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;


/**
 * @author Matthew.Norris
 * Default Process Definition (just to get you going!)
 * Pass this class name to the loader in order to turn process XMLs into 
 * something the core engine can use
 * @hibernate.class 
 */
public class ProcessDefinition extends AbstractProcessDefinition {
    private Long id;


    private Set taskDefinitions = new HashSet();
    private Set routingDefinitions = new HashSet();

    private ITaskDefinition firstTask = null;

    private IPropertyGroups propertyGroups = null;

    private String classConstruct = null;

    private String classDestruct = null;

    private Long version;
    
    private IProcessVersions processVersions;

    /**
     * @hibernate.property
     */
    public Long getVersion() {
        return this.version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public void setFirstTask(ITaskDefinition taskDef) {
        firstTask = taskDef;
        taskDefinitions.add(taskDef);
    }

    /**
     * @hibernate.property
     */
    public String getClassConstruct() {
        return this.classConstruct;
    }

    public void setClassConstruct(String className) {
        this.classConstruct = className;
    }

    /**
     * @hibernate.property
     */
    public String getClassDestruct() {
        return this.classDestruct;
    }

    public void setClassDestruct(String className) {
        this.classDestruct = className;
    }

    /**
     * @hibernate.many-to-one column="firstTaskDefId" not-null="false"
     *                        class="com.anite.zebra.ext.definitions.impl.TaskDefinition"
     *                        cascade="all" 
     */
    public ITaskDefinition getFirstTask() {
        return firstTask;
    }

    /**
     * @return Returns the name.
     */
    public String getName() {
        return getProcessVersions().getName();
    }

    /**
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return id;
    }

    /**
     * @param id
     *            The id to set.
     */
    public void setId(Long id) {
        this.id = id;
    }

    /**
     * @return Returns the taskDefs.
     */
    public ITaskDefinitions getTaskDefs() {
        return new TaskDefinitions(taskDefinitions);
       
    }

    public IRoutingDefinitions getRoutingDefs() {
        return new RoutingDefinitions(routingDefinitions);

    }

    /**
     * @return Returns the propertyGroups.
     * @hibernate.many-to-one column="propertyGroupsId" not-null="true"
     *                        class="com.anite.zebra.ext.definitions.impl.PropertyGroups"
     *                        cascade="all"
     */
    public IPropertyGroups getPropertyGroups() {
        return propertyGroups;
    }
    /**
     * @param propertyGroups The propertyGroups to set.
     */
    public void setPropertyGroups(IPropertyGroups propertyGroups) {
        this.propertyGroups = propertyGroups;
    }
   

    /**
     * @return Returns the taskDefinitions.
     * @hibernate.set cascade="all" inverse="false" lazy="true"
     * @hibernate.collection-key column="processDefId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.TaskDefinition"
     */
    public Set getTaskDefinitions() {
        return taskDefinitions;
    }
    /**
     * @param taskDefinitions The taskDefinitions to set.
     */
    public void setTaskDefinitions(Set taskDefinitions) {
        this.taskDefinitions = taskDefinitions;
    }
    /**
     * @return Returns the routingDefinitions.
     * @hibernate.set cascade="all" inverse="false" lazy="true"
     * @hibernate.collection-key column="processDefId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.RoutingDefinition"
     */
    public Set getRoutingDefinitions() {
        return routingDefinitions;
    }
    /**
     * @param routingDefinitions The routingDefinitions to set.
     */
    public void setRoutingDefinitions(Set routingDefinitions) {
        this.routingDefinitions = routingDefinitions;
    }
    /**
     * @return Returns the processVersions.
     * @hibernate.many-to-one column="processVersionsId" not-null="true"
     *                        class="com.anite.zebra.ext.definitions.impl.ProcessVersions"
     *                        cascade="all"
     */
    public IProcessVersions getProcessVersions() {
        return processVersions;
    }
    /**
     * @param processVersions The processVersions to set.
     * 
     */
    public void setProcessVersions(IProcessVersions processVersions) {
        this.processVersions = processVersions;
    }
}
