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
import java.util.Set;

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.ext.definitions.api.IPropertyGroups;
import com.anite.zebra.ext.definitions.api.IPropertyGroupsAware;

/**
 * @author Matthew.Norris
 * 
 * Default Task Definition (just to get you going!) Pass this class name to the
 * loader in order to turn process XMLs into something the core engine can use
 * @hibernate.class
 */
public class TaskDefinition implements ITaskDefinition, IPropertyGroupsAware {
    private String name;

    private Long id;

    private boolean synchronise;
    
    private boolean auto;

    private String className;

    private String classDestruct = null;

    private String classConstruct = null;

    private IPropertyGroups propertyGroups;

    private Set routingOut = new HashSet();

    private Set routingIn = new HashSet();    
    
    public void setSynchronise(boolean synchronise){
        this.synchronise=synchronise;
    }

    /**
     * @param auto The auto to set.
     */
    protected void setAuto(boolean auto) {
        this.auto = auto;
    }
    /**
     * @param propertyGroups The propertyGroups to set.
     */
    public void setPropertyGroups(IPropertyGroups propertyGroups) {
        this.propertyGroups = propertyGroups;
    }
    /**
     * @param routingIn The routingIn to set.
     */
    protected void setRoutingIn(Set routingIn) {
        this.routingIn = routingIn;
    }
    /**
     * @param routingOut The routingOut to set.
     */
    protected void setRoutingOut(Set routingOut) {
        this.routingOut = routingOut;
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
    public void setId(Long guid) {
        this.id = guid;
    }

    /**
     * @return Returns the name.
     * @hibernate.property
     */
    public String getName() {
        return name;
    }

    /**
     * @param name
     *            The name to set.
     */
    public void setName(String name) {
        this.name = name;
    }


    /**
     * @param auto
     *            The auto to set.
     */
    public void setAuto(Boolean auto) {
        this.auto = auto.booleanValue();
    }

    /**
     * Retunr the class name to use to instantiate a task
     * 
     * @return Returns the className.
     * @hibernate.property
     */
    public String getClassName() {
        return className;
    }

    /**
     * @param className
     *            The className to set.
     */
    public void setClassName(String className) {
        this.className = className;
    }

    /**
     * @return Returns the propertyGroups.
     * @hibernate.many-to-one column="propertyGroupsId" not-null="false"
     *                        class="com.anite.zebra.ext.definitions.impl.PropertyGroups"
     *                        cascade="save-update"
     */
    public IPropertyGroups getPropertyGroups() {
        return propertyGroups;
    }



    

    /**
     * @hibernate.property
     */
    public String getClassConstruct() {
        return this.classConstruct;
    }

    public void setClassConstruct(String className) {
        this.classConstruct = className;
    }

    /**
     * @hibernate.property
     */
    public String getClassDestruct() {
        return this.classDestruct;
    }

    public void setClassDestruct(String className) {
        this.classDestruct = className;
    }

    /**
     * @hibernate.property
     */
    public boolean isAuto() {
        return this.auto;
    }

    /**
     * @hibernate.property
     */
    public boolean getSynchronise() {
        return this.synchronise;
    }
    
    /**
     */
    public boolean isSynchronised() {
        return this.synchronise;
    }
    /**
     * @return Returns the routingIn.
     * @hibernate.set cascade="all" inverse="false" lazy="true"
     * @hibernate.collection-key column="taskDefRoutingInId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.RoutingDefinition"
     */
    public Set getRoutingIn() {
        return routingIn;
    }
    /**
     * @return Returns the routingOut.
     * @hibernate.set cascade="all" inverse="false" lazy="true"
     * @hibernate.collection-key column="taskDefRoutingOutId"
     * @hibernate.collection-one-to-many class="com.anite.zebra.ext.definitions.impl.RoutingDefinition"
     */
    public Set getRoutingOut() {
        return routingOut;
    }
}