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

import java.util.Iterator;

import junit.framework.TestCase;

import com.anite.zebra.ext.definitions.impl.Properties;

/**
 * @author Eric Pugh
 * 
 * TODO To change the template for this generated type comment go to Window -
 * Preferences - Java - Code Style - Code Templates
 */
public class PropertiesTest extends TestCase {

    private Properties props = null;

    public void setUp() {
        props = new Properties();
        props.put("bool", "true");
        props.put("long", "12312");
        props.put("string", "Hi!");
    }

    public void testSetGetName() {
        props.setName("name");
        assertEquals("name", props.getName());
    }

    public void testGet() {
        assertEquals("12312", props.get("long").toString());
    }

    public void testGetString() {
        assertEquals("12312", props.getString("long"));
    }

    public void testGetLongAsObj() {
        assertEquals(new Long(12312), props.getLongAsObj("long"));
    }

    public void testGetLong() {
        assertEquals(12312, props.getLong("long"));
    }
    
    public void testGetIntegerAsObj() {
        assertEquals(new Integer(12312), props.getIntegerAsObj("long"));
    }

    public void testGetInteger() {
        assertEquals(12312, props.getInteger("long"));
    }    

    public void testGetBooleanAsObj() {
        assertEquals(Boolean.TRUE, props.getBooleanAsObj("bool"));

    }

    public void testGetBoolean() {
        assertEquals(true, props.getBoolean("bool"));
    }

    public void testContainsKey() {
       
        assertFalse(props.containsKey("theMissingBoolean"));
        assertTrue(props.containsKey("bool"));
       
    }    
    
    public void testIteratorAsMapEntries() {
        
       Iterator i=props.keys();
       assertTrue(i.hasNext());
       while(i.hasNext()){
           assertTrue(i.next() instanceof String);
       }
        
     }     

}