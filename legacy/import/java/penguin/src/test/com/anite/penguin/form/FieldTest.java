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

package com.anite.penguin.form;

import java.util.ArrayList;

import junit.framework.TestCase;

import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben.Gidley
 * @author Shaun Campbell
 */
public class FieldTest extends TestCase{
    
    private static final String BOB_234 = "Bob[234]";
    public void testSuffix(){
        Field bob = new Field();
        bob.setName(BOB_234);
        assertEquals(bob.getMultipleNameSuffix(), "234");
        assertEquals(bob.getNameWithoutSuffix(), "Bob");
        assertEquals(bob.getName(), BOB_234);
    }
    
    public void testReset(){
        Field wibble = new Field();
        wibble.setName("Wibble");
        wibble.setValue("Bob");
        wibble.setValid(false);
        
        wibble.reset();
        
        assertTrue(wibble.isValid());
        assertEquals(wibble.getValue(), "");
        
    }
    
    public void testSetValue(){
    	Field field = new Field();
    	field.setName("Bob");
    	field.setValue(null);
    	assertEquals(field.getValue(),"");
    	String[] values = field.getValues();
    	assertEquals(values.length, 1);
    	assertEquals(values[0],"");
    }
    
    public void testDefault(){
    	Field field = new Field();
    	field.setName("Harry");
    	field.setDefaultValue("Wibble");
    	assertTrue(field.isDefault());
    	assertEquals(field.getValue(), "Wibble");
    	field.setDefault(false);
    	field.setDefaultValue("Bob");
    	assertEquals(field.getValue(), "Wibble");
    }
    
    public void testMultipleFields(){
        FormTool form = new FormTool();
        Field field1 = new Field();
        field1.setName("Bob[1]");
        Field field2 = new Field();
        field2.setName("Bob[2]");
        field2.setValue("Add");
        Field field3 = new Field();
        field3.setName("Jim"); 
        Field field4 = new Field();
        field4.setName("Ted[a]");        
        Field field5 = new Field();
        field5.setName("Ted[b]");
        field5.setValue("Edit");
        form.getFields().put(field1.getName(), field1);
        form.getFields().put(field2.getName(), field2);
        form.getFields().put(field3.getName(), field3);
        form.getFields().put(field4.getName(), field4);
        form.getFields().put(field5.getName(), field5);
        
        assertEquals(form.whichButtonClicked("Bob"),"2");
        assertEquals(form.whichButtonClicked("Ted"),"b");
        assertEquals(form.whichButtonClicked("Jim"),"");
        assertEquals(form.whichButtonClicked("Ben"),"");
    }
    
    public void testFieldCopy(){
        FormTool form = new FormTool();
        Field field1 = new Field();
        field1.setForm(form);
        field1.setId("field1");
        field1.setHtmlClass("field");
        field1.setStyle("fieldstyle");
       	field1.setTitle("fieldtitle");
        field1.setName("fieldname");
        String[] values = { "value1", "value2"};
        field1.setValues( values );
        field1.setQuickHelp("field help");
        field1.setAccessKey("a");
        field1.setDisabled(true);
        field1.setReadOnly(true);
        field1.setTabIndex(1);
        field1.setSize("30");
        field1.setMaxLength("50");
        Option[] options = new Option[2];
        Option option = new Option();
        option.setCaption("Option 1 caption");
        option.setValue("Option 1 value");
        options[0] = option;
        option = new Option();
        option.setCaption("Option 2 caption");
        option.setValue("Option 2 value");
        options[1] = option;
        field1.setOptions(options);
        ArrayList messages = new ArrayList();
        messages.add("First message");
        messages.add("Second message");
        field1.setMessages(messages);
        field1.setValid(false);
        field1.setDefault(false);
        form.getFields().put(field1.getName(),field1);
 

        Field field2 = form.getField("fieldname[2]");
        field1 = null;
        
        assertEquals(field2.getId(),"field1");
        assertEquals(field2.getHtmlClass(),"field");
        assertEquals(field2.getStyle(),"fieldstyle");
        assertEquals(field2.getTitle(),"fieldtitle");
        assertEquals(field2.getName(),"fieldname[2]");
        
        assertEquals(field2.getQuickHelp(),"field help");
        assertEquals(field2.getAccessKey(),"a");
        assertEquals(field2.isDisabled(),true);
        assertEquals(field2.isReadOnly(),true);
        assertEquals(field2.getTabIndex(),1);
        assertEquals(field2.getSize(),"30");
        assertEquals(field2.getMaxLength(),"50");
        
        assertEquals(field2.getOptions()[0].getCaption(),"Option 1 caption");
        assertEquals(field2.getOptions()[0].getValue(),"Option 1 value");
        assertEquals(field2.getOptions()[1].getCaption(),"Option 2 caption");
        assertEquals(field2.getOptions()[1].getValue(),"Option 2 value");
        
        assertEquals((String) field2.getMessages().get(0),"First message");
        assertEquals((String) field2.getMessages().get(1),"Second message");

        assertEquals(field2.isValid(),false);
        assertEquals(field2.isDefault(),false);
      
    }
}
