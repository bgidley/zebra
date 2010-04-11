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

import com.anite.zebra.ext.state.hibernate.HibernateLock;

/**
 * Represents a lock
 * Extended to force hibernate to generate it
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 * @author Ben.Gidley
 */
public class AntelopeLock extends HibernateLock {

    /**
     * 
     */
    public AntelopeLock() {
        super();

    }
    /**
     * @param id
     */
    public AntelopeLock(Long id) {
        super(id);

    }
    /**
     * @hibernate.id generator-class="assigned"
     */
    public Long getProcessInstanceId() {
        // TODO Auto-generated method stub
        return super.getProcessInstanceId();
    }
}
