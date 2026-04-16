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
import java.util.Iterator;
import java.util.Set;

import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.JoinTable;
import javax.persistence.OneToMany;
import javax.persistence.Transient;

import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.api.IProcessVersions;

/**
 * Extends Process Versions to make XDoclet read tags
 * 
 * @author Eric Pugh
 * @author Ben Gidley
 * @author michael jones
 */
@Entity
public class ZebraProcessVersions implements IProcessVersions {

    private Long id;

    private String name;

    private Set<IProcessVersion> processVersions = new HashSet<IProcessVersion>();

    /**
     * @return Returns the id. 
     */
    @Id @GeneratedValue
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
     * @return Returns the name.
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

    /**
     * @param processVersions
     *            The processVersions to set.
     */
    public void setProcessVersions(Set<IProcessVersion> processVersions) {
        this.processVersions = processVersions;
    }

    @OneToMany(targetEntity = ZebraProcessDefinition.class, cascade = CascadeType.ALL)
    @JoinTable(name = "processVersionProcesses", joinColumns = { @JoinColumn(name = "processVersionId") }, inverseJoinColumns = @JoinColumn(name = "processDefinitionId"))
    public Set<IProcessVersion> getProcessVersions() {
        return processVersions;
    }

    public void addProcessVersion(IProcessVersion processVersion) {
        processVersion.setProcessVersions(this);
        processVersions.add(processVersion);
    }

    @Transient
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
}
