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

/**
 * Represents a lock on a process instance
 * This is NOT foreigned keyed as it does not need to be
 * and it needs to be quick and simple 
 * 
 * This is keyed on ProcessID so we can ensure safety
 * in a cluster
 * 
 * @author Ben.Gidley
 * @hibernate.class
 */
public class HibernateLock {    
    
    private Long processInstanceId;
    
    public HibernateLock(){        
    }
    
    /**
     * Constructor for creating a lock
     * @param id
     */
    public HibernateLock(Long id){
        this.processInstanceId = id;
    }
    
    /**
     * @hibernate.id generator-class="assigned"
     * @return Returns the processInstanceId.
     */
    public Long getProcessInstanceId() {
        return processInstanceId;
    }
    /**
     * @param processInstanceId The processInstanceId to set.
     */
    public void setProcessInstanceId(Long processInstanceId) {
        this.processInstanceId = processInstanceId;
    }
}
