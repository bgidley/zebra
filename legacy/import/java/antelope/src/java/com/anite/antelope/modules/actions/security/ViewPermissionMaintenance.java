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
package com.anite.antelope.modules.actions.security;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.SecureAction;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;


/**
 * This is an empty class as the validation needs an endpoint for the 
 * formtool to be populated
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones</a>
 *
 */
public class ViewPermissionMaintenance extends SecureAction {

    /* (non-Javadoc)
     * @see org.apache.turbine.modules.actions.VelocitySecureAction#doPerform(org.apache.turbine.util.RunData, org.apache.velocity.context.Context)
     */
    public void doPerform(RunData data, Context context) throws Exception {
        // Just redirect back to the permissions page
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);
                
        Field selectField = (Field)form.getFields().get("select");
        
        if(selectField.getValue().equals("group")) {
            Field allocatedField = (Field)form.getFields().get("allocatedroles");
            allocatedField.setValue("");
        }        
        
        data.setScreenTemplate("security,PermissionMaintenance.vm");        
    }

}
