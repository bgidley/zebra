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

package com.anite.zebra.ext.definitions.impl;

import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.api.IPropertyGroupsAware;

/**
 * 
 * @author Eric Pugh
 * @hibernate.class
 *
 */
public class RoutingDefinition implements IRoutingDefinition, IPropertyGroupsAware {

    private Long id;

    private ITaskDefinition originatingTaskDefinition;

    private ITaskDefinition destinationTaskDefinition;

    private String name;

    private boolean parallel;

    private String conditionClass;
    
    private IPropertyGroups propertyGroups;


    /**
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return id;
    }

    /**
     * @return Returns the propertyGroups.
     * @hibernate.many-to-one column="propertyGroupsId" not-null="false"
     *                        class="com.anite.zebra.ext.definitions.impl.PropertyGroups"
     *                        cascade="save-update"
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
    public void setId(Long guid) {
        this.id = guid;
    }
       
    
    /**
     * @hibernate.property
     */
    public String getName() {
        return this.name;
    }

    public void setName(String name) {
        this.name = name;
    }

    /**
     * @hibernate.property
     */
    public boolean getParallel() {
        return this.parallel;
    }

    public void setParallel(boolean parallel) {
        this.parallel = parallel;
    }

    /**
     * @hibernate.property
     */
    public String getConditionClass() {
        return this.conditionClass;
    }

    public void setConditionClass(String conditionClass) {
        this.conditionClass = conditionClass;
    }

    /**
     * @hibernate.many-to-one column="destTaskDefId" not-null="false"
     *                        class="com.anite.zebra.ext.definitions.impl.TaskDefinition"
     *                        cascade="all" 
     */    
    public ITaskDefinition getDestinationTaskDefinition() {
        return destinationTaskDefinition;
    }
    
    public void setDestinationTaskDefinition(ITaskDefinition destinationTaskDefinition) {
        this.destinationTaskDefinition = destinationTaskDefinition;
    }

    /**
     * @hibernate.many-to-one column="origTaskDefId" not-null="false"
     *                        class="com.anite.zebra.ext.definitions.impl.TaskDefinition"
     *                        cascade="all" 
     */
    public ITaskDefinition getOriginatingTaskDefinition() {
        return originatingTaskDefinition;
    }

    public void setOriginatingTaskDefinition(ITaskDefinition originatingTaskDefinition) {
        this.originatingTaskDefinition = originatingTaskDefinition;
    }

}