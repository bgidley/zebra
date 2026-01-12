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

package com.anite.antelope.modules.actions.formSample;

import org.apache.turbine.modules.actions.VelocityAction;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.penguin.modules.tools.FormTool;

/**
 * Created 05-May-2004
 */
public class SimpleFormSubmit extends VelocityAction {
    
    
    /**
     * Process the simple form data
     * All control over the form flow is handled in this action. If you wish this
     * to be more automated look at the Zebra samples.
     */
    public void doPerform(RunData data, Context context) throws Exception {
        
        
        FormTool form  = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
        
        if (form.isAllValid()){
            // Passed all validation
            //@TODO do sample
            // Go to success URL
            data.setScreenTemplate("formSample,Success.vm");
        } else {
            // Failed some validation            

            // Return to previous screen
            data.setScreenTemplate("formSample,SimpleForm.vm");
        }
        
    }
}