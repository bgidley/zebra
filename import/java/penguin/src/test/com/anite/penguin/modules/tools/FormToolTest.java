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

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.ArrayList;

import junit.framework.TestCase;

import com.anite.penguin.form.Field;
import com.anite.penguin.form.Option;

/**
 * @author Ben.Gidley
 */
public class FormToolTest extends TestCase {

    private static final String BORRIS = "Borris";
    public void testSerialization() throws Exception {
        FormTool tool = new FormTool();
        
        Field field = new Field();
        field.setName(BORRIS);
        tool.getFields().put(BORRIS, field);
        
        Field field1 = new Field();
        field1.setForm(tool);
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
        tool.getFields().put(field1.getName(),field1);
        
        File file = new File("out.dat");
        
        
        
        FileOutputStream out = new FileOutputStream(file);
        ObjectOutputStream s = new ObjectOutputStream(out);
        s.writeObject(tool);        
        s.flush();
        
        ObjectInputStream in = new ObjectInputStream(new FileInputStream(file));
        FormTool loadedTool =(FormTool) in.readObject();
        
        assertEquals(loadedTool.toString(), tool.toString());
        
    }
    
}
