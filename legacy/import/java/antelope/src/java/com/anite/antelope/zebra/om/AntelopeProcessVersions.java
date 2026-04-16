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

import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.impl.ProcessVersions;

/**
 * Extends Process Versions to make XDoclet read tags
 * @author Eric Pugh
 * @author Ben Gidley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopeProcessVersions extends ProcessVersions {


    /**
     * @hibernate.property
     */
    public String getName() {

        return super.getName();
    }
    /**
     * @return Returns the id.
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return super.getId();
        
    }
    /**
     * @return Returns the process versions.
     * @hibernate.set cascade="all" inverse="false"
     * @hibernate.collection-key column="processVersionId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeProcessDefinition"
     * @hibernate.collection-cache usage="transactional"
     */
    public Set getProcessVersions() {
        return super.getProcessVersions();
    }
    
    /* (non-Javadoc)
     * @see com.anite.zebra.ext.definitions.impl.ProcessVersions#addProcessVersion(com.anite.zebra.ext.definitions.api.IProcessVersion)
     */
    public void addProcessVersion(IProcessVersion processVersion) {        
        super.addProcessVersion(processVersion);
        if (processVersion instanceof AntelopeProcessDefinition){
            ((AntelopeProcessDefinition) processVersion).setVersions(this);
        }
    }
    
}
