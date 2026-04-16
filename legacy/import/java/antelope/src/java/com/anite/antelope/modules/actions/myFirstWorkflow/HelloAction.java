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

package com.anite.antelope.modules.actions.myFirstWorkflow;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.myFirstWorkflow.Hello;
import com.anite.antelope.zebra.modules.actions.BaseWorkflowAction;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author Ben.Gidley
 */
public class HelloAction extends BaseWorkflowAction {


	/**
	 * Form has been submitted and passed validation
	 */
	protected boolean doPerform(RunData runData, Context context,
			AntelopeTaskInstance taskInstance,
			AntelopeProcessInstance processInstance, FormTool tool)
			throws Exception {

		// Get the validated name
		Field name = (Field) tool.getFields().get(Hello.NAME);

		// Save the name in the processInstance
		// Obviously in a real app this could be save it in the database
		AntelopePropertySetEntry nameEntry = new AntelopePropertySetEntry();
		nameEntry.setValue(name.getValue());
		processInstance.getPropertySet().put("name", nameEntry);

		// Indicate we are ready to move on
		taskInstance.setState(ITaskInstance.STATE_READY);
		
		return true;
	}

	/**
	 * This is set to true as we don't want doPerform to be
	 * called if validation fails.
	 */
	protected boolean enforceValidation() {

		return true;
	}

}