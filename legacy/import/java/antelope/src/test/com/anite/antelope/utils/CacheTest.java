/*
 * Copyright 2004 Anite - Central Government Division
 * http://www.anite.com/publicsector
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 * 
 * http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */
package com.anite.antelope.utils;

import java.util.Date;

import junit.framework.TestCase;

/**
 * This class 
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class CacheTest extends TestCase {

    public void testCache() {
        Cache cache = new Cache() {

            protected Object create(Object key) {
                return "hi";
            }
        };

        assertEquals("hi", cache.get(null));
    }

    public void testCacheWithKey() throws Exception {
        Cache cache = new Cache() {

            protected Object create(Object key) {
                Class clazz = (Class) key;
                if (clazz.getName().equals(String.class.getName())) {
                    return "string";
                } else if (clazz.getName().equals(Integer.class.getName())) {
                    return new Integer(1);
                } else if (clazz.getName().equals(Date.class.getName())) {
                    return new Date();
                } else {
                    return null;
                }
            }
        };

        assertEquals("string", cache.get(String.class));
        assertEquals(new Integer(1), cache.get(Integer.class));

        Date date = (Date) cache.get(Date.class);

        for (int i = 0; i < 100; i++) {
            assertSame(date, cache.get(Date.class));
            Thread.sleep(1);
            assertEquals(date.getTime(), ((Date)cache.get(Date.class)).getTime());
        }
    }
}