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

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;

/**
 * This class just extends the RoutingDefinition class to get the
 * various xdoclet tags.   
 * @author Eric Pugh
 * @author Ben GIdley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopeRoutingDefinition extends RoutingDefinition implements IXmlDefinition {

    private Long xmlId; 

    /**
     * @return Returns the xmlId.
     * @hibernate.property
     */
    public Long getXmlId() {
        return xmlId;
    }
    /**
     * @param xmlId The xmlId to set.
     */
    public void setXmlId(Long xmlId) {
        this.xmlId = xmlId;
    }
    /**
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return super.getId();
    }
    /**
     * @hibernate.property
     */
    public String getName() {
        return super.getName();
    }
    
    /**
     * @hibernate.many-to-one column="origTaskDefId" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopeTaskDefinition"
     *                        cascade="all" 
     */
    public ITaskDefinition getOriginatingTaskDefinition() {
        return super.getOriginatingTaskDefinition();
    }
    /**
     * @hibernate.property
     */
    public boolean getParallel() {
        return super.getParallel();
    }
    /**
     * @return Returns the propertyGroups.
     * @@hibernate.many-to-one column="propertyGroupsId" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopePropertyGroups"
     *                        cascade="save-update"
     */
    public IPropertyGroups getPropertyGroups() {
        return super.getPropertyGroups();
    }
    
    /**
     * @hibernate.property
     */
    public String getConditionClass() {
        return super.getConditionClass();
    }
    
    /**
     * @hibernate.many-to-one column="destTaskDefId" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopeTaskDefinition"
     *                        cascade="all" 
     */ 
    public ITaskDefinition getDestinationTaskDefinition() {
        return super.getDestinationTaskDefinition();
    }    
}
