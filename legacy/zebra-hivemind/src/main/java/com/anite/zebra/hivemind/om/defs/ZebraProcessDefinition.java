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

package com.anite.zebra.hivemind.om.defs;

import java.util.HashSet;
import java.util.Set;

import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.JoinTable;
import javax.persistence.ManyToOne;
import javax.persistence.OneToMany;
import javax.persistence.Transient;

import org.apache.commons.lang.exception.NestableException;
import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.util.PermissionSet;

import com.anite.zebra.core.definitions.api.IRoutingDefinitions;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinitions;
import com.anite.zebra.ext.definitions.api.AbstractProcessDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinitions;
import com.anite.zebra.ext.definitions.impl.TaskDefinitions;
import com.anite.zebra.hivemind.impl.ZebraSecurity;

/**
 * This class is used to provide a concrete ProcessDefinition for Hibernate 3.1 and
 * to store constants/convience functions to access properties and property
 * groups.
 * 
 * @author Eric Pugh
 * @author Ben Gidley
 * @author michael.jones 
 */
@Entity
public class ZebraProcessDefinition extends AbstractProcessDefinition {

    /* #com.anite.antelope.zebra.om.AntelopePropertyGroups Dependency_Link */
    /* Constants for Property Groups */
    private static final String PROPGROUP_VISIBILITY = "Visibility";

    private static final String PROPGROUP_INPUTS = "(Inputs)";

    private static final String PROPGROUP_OUTPUTS = "(Outputs)";

    /* Constants for visibility properties */
    private static final String PROP_DISPLAYNAME = "Display Name";

    private static final String PROP_DEBUG_FLOW = "DeubgFlow";

    /* Constants for security properties */
    private static final String PROPGROUP_SECURITY = "Security";

    private static final String PROP_START_PERMISSIONS = "Process Start Permissions";

    private static final String PROP_DYNAMIC_PERMISSIONS = "Dynamic Permissions";

    private Long id;

    private Set<ITaskDefinition> taskDefinitions = new HashSet<ITaskDefinition>();

    private Set routingDefinitions = new HashSet();

    private ITaskDefinition firstTask = null;

    private IPropertyGroups propertyGroups = null;

    private String classConstruct = null;

    private String classDestruct = null;

    private Long version;

    private IProcessVersions processVersions;

    @Id @GeneratedValue
    public Long getId() {
        return this.id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @OneToMany(targetEntity = ZebraTaskDefinition.class, cascade = CascadeType.ALL)
    @JoinTable(name = "processTaskDefinitions", joinColumns = { @JoinColumn(name = "processDefinitionId") }, inverseJoinColumns = @JoinColumn(name = "taskDefinitionId"))
    public Set getTaskDefinitions() {
        return this.taskDefinitions;
    }

    /**
     * @param taskDefinitions The taskDefinitions to set.
     */
    public void setTaskDefinitions(Set<ITaskDefinition> taskDefinitions) {
        this.taskDefinitions = taskDefinitions;
    }

    public void setFirstTask(ITaskDefinition taskDef) {
        firstTask = taskDef;
        taskDefinitions.add(taskDef);
    }

    public String getClassConstruct() {
        return this.classConstruct;
    }

    public String getClassDestruct() {
        return this.classDestruct;
    }

    @ManyToOne(cascade = { CascadeType.ALL }, targetEntity = ZebraTaskDefinition.class)
    @JoinColumn(name = "firstTaskDefId")
    public ITaskDefinition getFirstTask() {
        return this.firstTask;
    }

    public void setClassConstruct(String classConstruct) {
        this.classConstruct = classConstruct;
    }

    public void setClassDestruct(String classDestruct) {
        this.classDestruct = classDestruct;
    }

    @ManyToOne(cascade = { CascadeType.ALL }, targetEntity = ZebraPropertyGroups.class)
    @JoinColumn(name = "propertyGroupsId")
    public IPropertyGroups getPropertyGroups() {
        return this.propertyGroups;
    }

    @ManyToOne(cascade = { CascadeType.PERSIST, CascadeType.MERGE }, targetEntity = ZebraProcessVersions.class)
    @JoinColumn(name = "versionId")
    public IProcessVersions getProcessVersions() {
        return this.processVersions;
    }

    public void setProcessVersions(IProcessVersions processVersions) {
        this.processVersions = processVersions;
    }

    @OneToMany(targetEntity = ZebraRoutingDefinition.class, cascade = CascadeType.ALL)
    @JoinTable(name = "processDefinitionRoutings", joinColumns = { @JoinColumn(name = "processDefinitionId") }, inverseJoinColumns = @JoinColumn(name = "routingDefinitionId"))
    public Set getRoutingDefinitions() {
        return this.routingDefinitions;
    }

    /**
     * @param routingDefinitions The routingDefinitions to set.
     */
    public void setRoutingDefinitions(Set routingDefinitions) {
        this.routingDefinitions = routingDefinitions;
    }

    public Long getVersion() {
        return this.version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    @Transient
    /* Custom Helper method to get property groups */
    private IProperties getVisibilityProperties() {
        return getPropertyGroups().getProperties(PROPGROUP_VISIBILITY);
    }

    @Transient
    public IProperties getInputs() {
        return getPropertyGroups().getProperties(PROPGROUP_INPUTS);
    }

    @Transient
    public IProperties getOutputs() {
        return getPropertyGroups().getProperties(PROPGROUP_OUTPUTS);
    }

    @Transient
    public IProperties getSecurityProperties() {
        return getPropertyGroups().getProperties(PROPGROUP_SECURITY);
    }

    /* Custom Helper methods to quickly get visibility properties */
    @Transient
    public String getDisplayName() {
        String displayName = getVisibilityProperties().getString(PROP_DISPLAYNAME);
        if (displayName == null) {
            displayName = getName();
        }
        return displayName;

    }

    @Transient
    public String getName() {
        return getProcessVersions().getName();
    }

    @Transient
    public boolean getDebugFlow() {
        return getVisibilityProperties().getBoolean(PROP_DEBUG_FLOW);
    }

    /* Helpers to get security properties */
    @Transient
    public String getDynamicPermissions() {
        return this.getSecurityProperties().getString(PROP_DYNAMIC_PERMISSIONS);
    }

    @Transient
    private String getStartPermissionsText() {
        return this.getSecurityProperties().getString(PROP_START_PERMISSIONS);
    }

    @Transient
    public PermissionSet getStartPermissions() throws NestableException {
        ZebraSecurity security = (ZebraSecurity) RegistryManager.getInstance().getRegistry().getService(
                "zebra.zebraSecurity", ZebraSecurity.class);
        return security.getPermissionSet(this.getStartPermissionsText());

    }

    @Transient
    public ITaskDefinitions getTaskDefs() {
        return new TaskDefinitions(taskDefinitions);
    }

    @Transient
    public IRoutingDefinitions getRoutingDefs() {
        return new RoutingDefinitions(routingDefinitions);
    }

    @Transient
    public void setPropertyGroups(IPropertyGroups propertyGroups) {
        this.propertyGroups = propertyGroups;
    }

}