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

package com.anite.penguin.modules.tools;

import java.util.Set;

import junit.framework.TestCase;

import com.anite.penguin.form.Field;

/**
 * @author Ben.Gidley
 */
public class FieldMapTest extends TestCase {

    private static final String WIBBLE = "Wibble";
    private static final String BOB_345 = "Bob[345]";
    private static final String BOB_234 = "Bob[234]";
    private FieldMap fieldMap = new FieldMap();
    private Field bob;
    private Field bob2;
    private Field wibble2;
    
    protected void setUp() throws Exception {
        bob = new Field();
        bob.setName(BOB_234);
        bob2 = new Field();
        bob2.setName(BOB_345);
        wibble2 = new Field();
        wibble2.setName(WIBBLE);
        
        fieldMap.put(bob.getName(), bob);
        fieldMap.put(bob2.getName(), bob2);
        fieldMap.put(wibble2.getName(), wibble2);
    }
    public void testGetMultipleFields() {
        Set fields = fieldMap.getMultipleFields("Bob");
        assertEquals(fields.size(),2);
        assertTrue(fields.contains(bob));
        assertTrue(fields.contains(bob2));
        assertFalse(fields.contains(wibble2));
    }

    public void testIsFieldPresent() {
        assertTrue(fieldMap.isFieldPresent(BOB_234));
        assertTrue(fieldMap.isFieldPresent("Bob"));
        assertFalse(fieldMap.isFieldPresent("Bo"));
        
    }
    
    public void testToString(){
        assertTrue(fieldMap.toString().length()>0);
    }

}
