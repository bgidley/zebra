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

import com.anite.zebra.ext.definitions.impl.PropertyGroups;

/**
 * This class just extends the PrpertyElement class to get the
 * various xdoclet tags.  Argh.
 *
 * @author Eric Pugh
 * @author Ben Gidley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopePropertyGroups extends PropertyGroups {

    /*#com.anite.antelope.zebra.om.AntelopePropertyElement Dependency_Link*/
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
     * @hibernate.collection-key column="propertyGroupId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopePropertyElement"
     * @hibernate.collection-cache usage="transactional"
     */
    protected Set getPropertyElements() {
        return super.getPropertyElements();
    }
}