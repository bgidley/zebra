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

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import junit.framework.TestCase;

import com.anite.zebra.ext.definitions.api.IPropertyGroupsAware;

/**
 * @author Eric Pugh
 * 
 */
public class IPropertyGroupsAwareTest extends TestCase {



    public void testPropertyGroupsAware() {
        RoutingDefinition rd = new RoutingDefinition();
        ProcessDefinition pd = new ProcessDefinition();
        TaskDefinition td = new TaskDefinition();
        List l = new ArrayList();
        l.add(rd);
        l.add(pd);
        l.add(td);
        for (Iterator i = l.iterator();i.hasNext();){
            IPropertyGroupsAware ipga = (IPropertyGroupsAware)i.next();
            createPropertyGroups(ipga);
        }
        assertNotNull(rd.getPropertyGroups());
        assertNotNull(pd.getPropertyGroups());
        assertNotNull(td.getPropertyGroups());
        
    }
    
    protected void createPropertyGroups(IPropertyGroupsAware pgAware){
        pgAware.setPropertyGroups(new PropertyGroups());
    }


}