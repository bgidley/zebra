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

import com.anite.zebra.ext.definitions.impl.PropertyElement;

/**
 * This class just extends the PropertyElement class to get the
 * various xdoclet tags.  
 * 
 * @author Eric Pugh
 * @author Ben Gidley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopePropertyElement extends PropertyElement {

    public AntelopePropertyElement() {
        super();
    }
   
    public AntelopePropertyElement(String group, String key, String value) {
        super(group, key, value);
    }
   
    
    /**
     * @return Returns the id.
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return super.getId();
    }

    /**
     * @return Returns the group.
     * @hibernate.property column="groupCol"
     */
    public String getGroup() {
        return super.getGroup();
    }
    /**
     * @return Returns the key.
     * @hibernate.property column="keyCol"
     */
    public String getKey() {
        return super.getKey();
    }
    /**
     * @return Returns the value.
     * @hibernate.property column="valueCol"
     */
    public String getValue() {
        return super.getValue();
    }
}
