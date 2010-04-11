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

import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

import com.anite.penguin.form.Field;
import com.anite.penguin.form.MissingField;

/**
 * Field map
 * 
 * The only special feature of this over a normal map is it does not return null
 * if a field is missing Instead it returns a MissingField object This is to
 * help with CheckBoxes and the like which can be missing from the request.
 * 
 * Created 05-May-2004
 */
public class FieldMap extends HashMap {

    /** Version Flag for serialisation   */
    static final long serialVersionUID = 1L;
    
    /**
     * If at all possible returns a MissingField rather than a null.
     * 
     * @see java.util.Map#get(java.lang.Object)
     */
    public Object get(Object key) {
        Object value = super.get(key);

        if (value == null) {
            if (key != null && key instanceof String) {
                String keyString = (String) key;

                int offsetLeft = keyString.lastIndexOf("[");
                int offsetRight = keyString.lastIndexOf("]");

                if (offsetRight <= offsetLeft + 1) {
                    MissingField field = new MissingField();
                    
                    field.setName( keyString);
                    this.put(key, field);
                    return field;    
                } else {
                    Field master = (Field) this.get(keyString.substring(0, offsetLeft));
                    Field newField = new Field(master);
                    newField.setName(keyString);
                    this.put(keyString, newField);
                    return newField;
                }
                
                
            } else {
                return null;
            }
        } else {
            return (Field) value;
        }
    }
    
    /**
     * Fetches any fields in the form that being with the
     * base string
     * 
     * Useful for field where the fieldname[N] notation
     * has been used
     * @param baseString
     * @return
     */
    public Set getMultipleFields(String baseString){
        Set fields = new HashSet();
        
        Set keys = this.keySet();
        for (Iterator iter = keys.iterator(); iter.hasNext();) {
            String key = (String) iter.next();
            
            if (key.startsWith(baseString)){
                fields.add(this.get(key));
            }            
        }        
        return fields;
       
    }
    
    /**
     * Checks if a field is present (suffix aware)
     * @param fieldName
     * @return
     */
    public boolean isFieldPresent(String fieldName){
        Set keys = this.keySet();
        for (Iterator iter = keys.iterator(); iter.hasNext();) {
            String key = (String) iter.next();
            
            if (key.equals(fieldName)){
                return true;
            } else {
                Field field = (Field) this.get(key);
                if (field.getNameWithoutSuffix().equals(fieldName)){
                    return true;
                }
            }
                        
        }        
        return false;
    }
    
    /**
     * Debugger friendly toString function
     */
    public String toString() {
        StringBuffer value = new StringBuffer();
        Iterator keys = this.keySet().iterator();
        while (keys.hasNext()) {
            Field field = (Field) this.get(keys.next());
            value.append(field.getName());
            value.append(":");
            value.append(field.getValue());
            value.append("\n");
        }
        return value.toString();
    }
}