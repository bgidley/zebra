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
package com.anite.zebra.avalon.mocks;

import java.util.Set;

import com.anite.zebra.core.definitions.api.ITaskDefinition;

/**
 * @author Eric Pugh
 *
 */
public class MockTaskDefinition implements ITaskDefinition {

    /**
     * 
     */
    public MockTaskDefinition() {
        super();
        // TODO Auto-generated constructor stub
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getId()
     */
    public Long getId() {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#isAuto()
     */
    public boolean isAuto() {
        // TODO Auto-generated method stub
        return false;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getClassName()
     */
    public String getClassName() {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#isSynchronised()
     */
    public boolean isSynchronised() {
        // TODO Auto-generated method stub
        return false;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getRoutingOut()
     */
    public Set getRoutingOut() {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getRoutingIn()
     */
    public Set getRoutingIn() {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getClassConstruct()
     */
    public String getClassConstruct() {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.definitions.api.ITaskDefinition#getClassDestruct()
     */
    public String getClassDestruct() {
        // TODO Auto-generated method stub
        return null;
    }

}
