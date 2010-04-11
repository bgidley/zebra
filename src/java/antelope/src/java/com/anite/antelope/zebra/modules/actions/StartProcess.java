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

package com.anite.antelope.zebra.modules.actions;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * This is the standard action to start a workflow
 * @author Ben.Gidley
 */
public class StartProcess extends AbstractWorkflowRunTaskAction {

    private final static Log log = LogFactory.getLog(StartProcess.class);

    private static final String PROCESS_NAME = "processname";

    public void doPerform(RunData data, Context context) throws Exception {

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            Field processName = (Field) form.getFields().get(PROCESS_NAME);
            
            // TODO Check process creation permissions
            
            AntelopeProcessInstance processInstance = ZebraHelper.getInstance().createProcessPaused(
                    processName.getValue());
            ZebraHelper.getInstance().getEngine().startProcess(processInstance);
            
            // Process Helpers
            ProcessStartListener[] listeners = getListeners();
            if (listeners!=null){
            	for (int i = 0; i < listeners.length; i++) {
					ProcessStartListener listener = listeners[i];
					listener.processStarting(processInstance, data, form);					
				}
            }
            determineNextScreen(data, form, processInstance, context);
        }
    }

    /**
     * Here because it has to be
     */
    protected boolean isAuthorized(RunData data) throws Exception {
        return true;
    }
    
    /**
     * Overide this if you want listeners
     * @return
     */
    public ProcessStartListener[] getListeners(){
    	return null;
    }
}