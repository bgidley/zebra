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

import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

import com.anite.zebra.ext.definitions.api.IProperties;

/**
 * TODO This class is a mess and probably should be removed
 * @author Eric Pugh 
 */

public class Properties implements IProperties {

    private String name;

    private Map<String, String> properties = new HashMap<String, String>();

    public String getName() {
        return this.name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Object get(Object key) {
        return properties.get(key);
    }

    public String getString(String key) {
        return properties.get(key);
    }

    public Long getLongAsObj(String key) {
        return new Long(properties.get(key));
    }

    public long getLong(String key) {
        return Long.valueOf(properties.get(key));
    }

    public Integer getIntegerAsObj(String key) {
        return Integer.valueOf(properties.get(key));
        
    }

    public int getInteger(String key) {        
        return Integer.valueOf(properties.get(key));
    }

    public Boolean getBooleanAsObj(String key) {
        return convertStringToBoolean(properties.get(key));
    }

    public boolean getBoolean(String key) {
        return convertStringToBoolean(properties.get(key));
    }
    
    private Boolean convertStringToBoolean(String value){
        if (value.equalsIgnoreCase("Yes") || value.equalsIgnoreCase("True")){
            return true;
        } else {
            return false;
        }
    }

    public void put(String key, String value) {
        properties.put(key, value);
    }

    public boolean containsKey(String key) {       
        return properties.containsKey(key);
    }

    public Iterator keys() {       
        return properties.keySet().iterator();
    }

}