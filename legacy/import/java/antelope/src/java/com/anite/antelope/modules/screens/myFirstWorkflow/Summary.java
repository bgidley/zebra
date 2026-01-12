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

import java.sql.Date;
import java.text.SimpleDateFormat;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.modules.screens.BaseWorkflowScreen;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author John.Rae
 */
public class Summary extends BaseWorkflowScreen {

	/**
	 * Prepare Data
	 */
	protected void doBuildTemplate(RunData runData, Context context,
			AntelopeTaskInstance taskInstance, FormTool tool) throws Exception {

		SimpleDateFormat sdf = new SimpleDateFormat("dd/mm/yy");
		//no fields are used in the summary page so all the data is placed into the context

		context.put(Hello.NAME,
			((AntelopePropertySetEntry) ((AntelopeProcessInstance) taskInstance
					.getProcessInstance()).getPropertySet().get(
				Hello.NAME)).getValue());

		context.put(HowOldAreYou.AGE,
			((AntelopePropertySetEntry) ((AntelopeProcessInstance) taskInstance
					.getProcessInstance()).getPropertySet().get(
				HowOldAreYou.AGE)).getValue());

		//date is stored in the propertySet as an object (of type Date) so it needs casting back 
		Date expiryDate = (Date) ((AntelopePropertySetEntry) ((AntelopeProcessInstance) taskInstance
				.getProcessInstance()).getPropertySet().get(
			EnterExpiryDate.EXPIRY)).getObject();

		//then needs placing into context as a formatted string
		//it can be placed in as a date object but the format is then yyyy/mm/dd and we want dd/mm/yy
		context.put(EnterExpiryDate.EXPIRY, sdf.format(expiryDate));

	}

}