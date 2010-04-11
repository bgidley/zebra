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

package com.anite.antelope.modules.screens.myFirstWorkflow;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.modules.screens.BaseWorkflowScreen;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben.Gidley
 */
public class EnterExpiryDate extends BaseWorkflowScreen {

	public static final String	EXPIRY	= "expiry";

	/**
	 * Prepare Data if needed
	 */
	protected void doBuildTemplate(RunData runData, Context context,
			AntelopeTaskInstance taskInstance, FormTool tool) throws Exception {

		//put the name and age into the context to be displayed as text
		context.put(Hello.NAME,
			((AntelopePropertySetEntry) ((AntelopeProcessInstance) taskInstance
					.getProcessInstance()).getPropertySet().get(
				"name")).getValue());
		
		context.put(HowOldAreYou.AGE,
			((AntelopePropertySetEntry) ((AntelopeProcessInstance) taskInstance
					.getProcessInstance()).getPropertySet().get(
				HowOldAreYou.AGE)).getValue());

	}
}