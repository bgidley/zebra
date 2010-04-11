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


/**
 * 
 * @author Eric Pugh
 * @hibernate.class  
 */

public class PropertyElement {

    private String key;
    private String value;
    private String group;
    private Long id;

    public PropertyElement(){
        
    }
    public PropertyElement(String group, String key, String value){
        setGroup(group);
        setKey(key);
        setValue(value);
    }

    /**
     * @return Returns the group.
     * @hibernate.property
     */
    public String getGroup() {
        return group;
    }
    /**
     * @param group The group to set.
     */
    public void setGroup(String group) {
        this.group = group;
    }
    /**
     * @return Returns the id.
     * @hibernate.id generator-class="native"
     */
    public Long getId() {
        return id;
    }
    /**
     * @param id The id to set.
     */
    public void setId(Long id) {
        this.id = id;
    }

    /**
     * @return Returns the key.
     * @hibernate.property column="keyCol"
     */
    public String getKey() {
        return key;
    }

    /**
     * @return Returns the value.
     * @hibernate.property
     */
    public String getValue() {
        return value;
    }
    /**
     * @param value The value to set.
     */
    public void setValue(String value) {
        this.value = value;
    }
    /**
     * @param key
     *            The key to set.
     */
    public void setKey(String key) {
        this.key = key;
    }


}