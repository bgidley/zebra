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

import java.util.Set;

import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.OneToMany;

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
@Entity
public class ZebraPropertyGroups extends PropertyGroups {

    /*#com.anite.antelope.zebra.om.AntelopePropertyElement Dependency_Link*/
    /**
     * @return Returns the id.
     * @hibernate.id generator-class="native"
     */
	@Id @GeneratedValue
    public Long getId() {
        return super.getId();
    }

	@OneToMany(targetEntity = ZebraPropertyElement.class, cascade=CascadeType.ALL)
	//@JoinTable(table = @Table(name = "propertyGroupElements"), joinColumns = { @JoinColumn(name = "propertyGroupsId") }, inverseJoinColumns = @JoinColumn(name = "propertyId"))
    protected Set getPropertyElements() {
        return super.getPropertyElements();
    }
}