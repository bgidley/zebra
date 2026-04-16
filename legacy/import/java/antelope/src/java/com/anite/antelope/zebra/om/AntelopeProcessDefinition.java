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

package com.anite.antelope.zebra.om;

import java.util.Set;

import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.util.PermissionSet;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;

/**
 * This class is used to provide a concrete ProcessDefinition for Hibernate and to store constants/convience functions
 * to access properties and property groups.
 *
 * @author Eric Pugh
 * @author Ben Gidley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopeProcessDefinition extends ProcessDefinition {

    private final static Log log = LogFactory
            .getLog(AntelopeProcessDefinition.class);

    /*#com.anite.antelope.zebra.om.AntelopePropertyGroups Dependency_Link*/
    /* Constants for Property Groups */
    private static final String PROPGROUP_VISIBILITY = "Visibility";

    private static final String PROPGROUP_INPUTS = "(Inputs)";

    private static final String PROPGROUP_OUTPUTS = "(Outputs)";

    /* Constants for visibility properties */
    private static final String PROP_DISPLAYNAME = "Display Name";

    private static final String PROP_DEBUG_FLOW = "DeubgFlow";

    /* Constants for security properties*/
    private static final String PROPGROUP_SECURITY = "Security";

    private static final String PROP_START_PERMISSIONS = "Process Start Permissions";

    private static final String PROP_DYNAMIC_PERMISSIONS = "Dynamic Permissions";

    private AntelopeProcessVersions versions;

    /* Overidden functions to force XDoclet to read Hibernate tags */

    /**
     * @hibernate.property
     */
    public String getClassConstruct() {
        return super.getClassConstruct();
    }

    /**
     * @hibernate.property
     */
    public String getClassDestruct() {
        return super.getClassDestruct();
    }

    /**
     * @hibernate.many-to-one column="firstTaskDefId" not-null="false"
     *      class="com.anite.antelope.zebra.om.AntelopeTaskDefinition"
     *      cascade="all"
     */
    public ITaskDefinition getFirstTask() {
        return super.getFirstTask();
    }

    /**
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return super.getId();
    }

    /**
     * The name (resovled from the ProcessVersion
     */
    public String getName() {
        return super.getName();
    }

    /**
     * @return Returns the propertyGroups.
     * @hibernate.many-to-one column="propertyGroupsId" not-null="true"
     *                        class="com.anite.antelope.zebra.om.AntelopePropertyGroups"
     *                        cascade="all"
     */
    public IPropertyGroups getPropertyGroups() {
        return super.getPropertyGroups();
    }

    /**
     * @return Returns the routingDefinitions.
     * @hibernate.set cascade="all" inverse="false"
     * @hibernate.collection-key column="processDefId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeRoutingDefinition"
     * @hibernate.collection-cache usage="transactional"
     */
    public Set getRoutingDefinitions() {
        return super.getRoutingDefinitions();
    }

    /**
     * @return Returns the taskDefinitions.
     * @hibernate.set cascade="all" inverse="false"
     * @hibernate.collection-key column="processDefId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeTaskDefinition"
     * @hibernate.collection-cache usage="transactional"
     */
    public Set getTaskDefinitions() {
        return super.getTaskDefinitions();
    }

    /**
     * @hibernate.property
     */
    public Long getVersion() {
        return super.getVersion();
    }

    /* Custom Helper method to get property groups */
    private IProperties getVisibilityProperties() {
        return getPropertyGroups().getProperties(PROPGROUP_VISIBILITY);
    }

    public IProperties getInputs() {
        return getPropertyGroups().getProperties(PROPGROUP_INPUTS);
    }

    public IProperties getOutputs() {
        return getPropertyGroups().getProperties(PROPGROUP_OUTPUTS);
    }

    public IProperties getSecurityProperties() {
        return getPropertyGroups().getProperties(PROPGROUP_SECURITY);
    }

    /* Custom Helper methods to quickly get visibility properties */

    public String getDisplayName() {
        String displayName = getVisibilityProperties().getString(
                PROP_DISPLAYNAME);
        if (displayName == null) {
            displayName = getName();
        }
        return displayName;

    }

    public boolean getDebugFlow() {
        return getVisibilityProperties().getBoolean(PROP_DEBUG_FLOW);
    }

    /* Helpers to get security properties */

    public String getDynamicPermissions() {
        return this.getSecurityProperties().getString(PROP_DYNAMIC_PERMISSIONS);
    }

    private String getStartPermissionsText() {
        return this.getSecurityProperties().getString(PROP_START_PERMISSIONS);
    }

    /**
     * @hibernate.many-to-one column="versionId" not-null="true"
     *                        class="com.anite.antelope.zebra.om.AntelopeProcessVersions"
     *                        cascade="all"
     * @return Returns the versions.
     */
    public IProcessVersions getProcessVersions() {
        return super.getProcessVersions();
    }

    /**
     * @param versions The versions to set.
     */
    public void setVersions(IProcessVersions versions) {
        super.setProcessVersions(versions);
    }

    public PermissionSet getStartPermissions() throws NestableException {
        return ZebraHelper.getInstance().getPermissionSet(this.getStartPermissionsText());
    }    

}