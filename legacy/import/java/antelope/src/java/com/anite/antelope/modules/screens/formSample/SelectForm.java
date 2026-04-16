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

package com.anite.antelope.modules.screens.formSample;

import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.penguin.form.Field;
import com.anite.penguin.form.Option;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Created 20-May-2004
 */
public class SelectForm extends VelocityScreen {

    
private static final String SIZE = "size";
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        
        // Set up size field
        Field size = (Field) form.getFields().get(SIZE);

        Option[] sizes = new Option[3];
        sizes[0] = new Option();
        sizes[0].setValue("0");
        sizes[0].setCaption("Small");
        sizes[1] = new Option();
        sizes[1].setValue("1");
        sizes[1].setCaption("Medium");
        sizes[2] = new Option();
        sizes[2].setValue("2");
        sizes[2].setCaption("Large");
        
        size.setOptions(sizes);
    }
}