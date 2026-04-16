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

package com.anite.zebra.ext.state.hibernate;

import java.util.HashSet;
import java.util.Set;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 *
 * @author Eric Pugh
 * @author Ben Gidley
 *
 * @hibernate.class
 *  table="PROCESS_INSTANCE"
 */

public class HibernateProcessInstance implements IProcessInstance{
    private Long processInstanceId = null;
    private IProcessDefinition processDef = null;
    private Set taskInstances = new HashSet();  
	
    /**
	 * @param processDef The processDef to set.
	 */
	protected void setProcessDef(IProcessDefinition processDef) {
		this.processDef = processDef;
	}
	/**
	 * @param taskInstances The taskInstances to set.
	 */
	protected void setTaskInstances(Set taskInstances) {
		this.taskInstances = taskInstances;
	}
    private long state;

    /**
     * @hibernate.id generator-class="native" column="processInstanceId"
     *
     * @return Returns the id.
     */
    public Long getProcessInstanceId() {
        return processInstanceId;
    }

    /**
     *
     * @param id
     *            The id to set.
     */
    public void setProcessInstanceId(Long id) {
        this.processInstanceId = id;
    }
    
    public IProcessDefinition getProcessDef() throws DefinitionNotFoundException {     
        return processDef;
    }    

    /**
     * @hibernate.property
     */
    public long getState() {
        return state;
    }
    
	/**
	 * @hibernate.set cascade="all" lazy="true" inverse="true"
	 * @hibernate.collection-key column="processInstanceId"
	 * @hibernate.collection-one-to-many
	 * class="com.anite.zebra.ext.state.hibernate.HibernateTaskInstance"
	 * @return
	 */    
    public Set getTaskInstances() {
        return taskInstances;
    }
    
    public void addTaskInstance(HibernateTaskInstance taskInstance){
    	taskInstance.setProcessInstance(this);
    	getTaskInstances().add(taskInstance);
    }
    
    public void setState(long state) {
        this.state = state;

    }
}