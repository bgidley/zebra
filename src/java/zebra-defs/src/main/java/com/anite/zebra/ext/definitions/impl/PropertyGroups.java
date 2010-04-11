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

import com.anite.zebra.ext.definitions.api.IProperties;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;

/**
 * @author Eric Pugh
 * @hibernate.class table="PropertyGroups"
 */

public class PropertyGroups implements IPropertyGroups {
    private Long id;

    private Set propertyElements = new HashSet();

    public IProperties getProperties(String name) {
        Properties p = new Properties();
        p.setName(name);
        for (Iterator i = propertyElements.iterator(); i.hasNext();) {
            PropertyElement pe = (PropertyElement) i.next();
            if (pe.getGroup().equalsIgnoreCase(name)) {
                p.put(pe.getKey(), pe.getValue());
            }
        }
        return p;
    }

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

    public void addPropertyElement(PropertyElement pe) {
        propertyElements.add(pe);
    }

    /**
     * @return Returns the process versions.
     * @hibernate.set cascade="all" inverse="false" lazy="true"
     * @hibernate.collection-key column="propertyGroupId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.PropertyElement"
     */  
    protected Set getPropertyElements() {
        return propertyElements;
    }

    protected void setPropertyElements(Set propertyElements) {
        this.propertyElements = propertyElements;
    }
}