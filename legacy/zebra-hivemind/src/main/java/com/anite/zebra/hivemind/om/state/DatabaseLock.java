/*
 * Copyright 2004, 2005 Anite - Central Government Division
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

package com.anite.zebra.hivemind.om.state;

import javax.persistence.Entity;
import javax.persistence.Id;

/**
 * Represents a lock on a process instance
 * This is NOT foreigned keyed as it does not need to be
 * and it needs to be quick and simple 
 * 
 * This is keyed on ProcessID so we can ensure safety
 * in a cluster
 * 
 * TODO Review if the locking in Hibernate 3 works!
 * 
 * @author Ben.Gidley
 */
@Entity
public class DatabaseLock {    
    
    private Long processInstanceId;
    
    public DatabaseLock(){  
    	//noop
    }
    
    /**
     * Constructor for creating a lock
     * @param id
     */
    public DatabaseLock(Long id){
        this.processInstanceId = id;
    }
    
    /**
     * @return Returns the processInstanceId.
     */
    @Id
    public Long getProcessInstanceId() {
        return this.processInstanceId;
    }
    /**
     * @param processInstanceId The processInstanceId to set.
     */
    public void setProcessInstanceId(Long processInstanceId) {
        this.processInstanceId = processInstanceId;
    }
}
