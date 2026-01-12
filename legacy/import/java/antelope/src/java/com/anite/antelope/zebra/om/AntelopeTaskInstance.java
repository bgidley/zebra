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

import java.util.HashMap;
import java.util.Map;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;

/**
 * @hibernate.class lazy="true"
 * @hibernate.query name="AllUsersTasks" query="from AntelopeTaskInstance ati where ati.showInTaskList = :show and ati.centre= :centre"
 * @hibernate.query name="UsersTasks" query="from AntelopeTaskInstance ati where (ati.taskOwner = :user or ati.taskOwner is null) and ati.showInTaskList = :show"
 * @hibernate.cache usage="transactional"
 * @author Ben.Gidley
 */
public class AntelopeTaskInstance extends AbstractAntelopeTaskInstance {
    
    public static final long KILLED = 66;
    public static final String PAUSED_FORM_DETAILS = "paused_form_details";
    
    
    
    /** The property set catch all for anything at all 
     * It will be emptied when the history item is constructed 
     * 
	 * @link aggregation <{com.anite.antelope.zebra.om.AntelopePropertySetEntry}>
	 * @directed directed
	 * @supplierCardinality 0..*
	 *
     * 
     * */
    private Map propertySet = new HashMap();


    /**
     * Default Constructor
     */
    public AntelopeTaskInstance() {
        super();
    }

    /**
     * Copy Constructor
     * @param taskInstance
     * @throws DefinitionNotFoundException
     */
    public AntelopeTaskInstance(AbstractAntelopeTaskInstance taskInstance)
            throws DefinitionNotFoundException {
        super(taskInstance);

    }
    
    /** 
     * @hibernate.map cascade="all" lazy="true"
     * @hibernate.collection-index column="propertyKey" type="string"  
     * @hibernate.collection-key column="taskInstanceId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopePropertySetEntry"
     * @hibernate.collection-cache usage="transactional"
     * @return
     */
    public Map getPropertySet() {
        return propertySet;
    }
    /**
     * @param propertySetEntries The propertySetEntries to set.
     */
    public void setPropertySet(Map propertySetEntries) {
        this.propertySet = propertySetEntries;
    }
}
