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
import java.util.Iterator;
import java.util.Set;

import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.api.IProcessVersions;

/**
 * 
 * @author Eric Pugh
 * @hibernate.class
 */
public class ProcessVersions implements IProcessVersions {

    private Long id;

    private Set processVersions = new HashSet();
    
    private String name;

    /**
     * @return Returns the id.
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
     * @param processVersions
     *            The processVersions to set.
     */
    public void setProcessVersions(Set processVersions) {
        this.processVersions = processVersions;
    }

    public IProcessVersion getLatestProcessVersion() {
        IProcessVersion bestVersion = null;
        for (Iterator it = processVersions.iterator(); it.hasNext();) {
            IProcessVersion processVersion = (IProcessVersion) it.next();
            if (bestVersion == null) {
                bestVersion = processVersion;
            } else if (processVersion.getVersion().longValue() > bestVersion.getVersion().longValue()) {
                bestVersion = processVersion;
            }
        }
        return bestVersion;
    }

    public void addProcessVersion(IProcessVersion processVersion) {
        processVersion.setProcessVersions(this);
        processVersions.add(processVersion);

    }
    /**
     * @return Returns the process versions.
     * @hibernate.set cascade="all" inverse="true" lazy="true"
     * @hibernate.collection-key column="processVersionId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.ProcessDefinition"
     */
    public Set getProcessVersions() {
        return processVersions;
    }
    /**
     * @return Returns the name.
     * @hibernate.property
     */
    public String getName() {
        return name;
    }
    /**
     * @param name The name to set.
     */
    public void setName(String name) {
        this.name = name;
    }
}