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
package com.anite.antelope.zebra.om;

import java.util.Set;

import junit.framework.TestCase;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.zebra.ext.definitions.impl.ProcessDefinition;

/**
 * @author martin.rouen
 */
public class TurbineAntelopePropertyGroupsTest extends TestCase {
	private ZebraHelper zebraHelper;

	private AntelopePropertyGroups propertyGroups;

	protected void setUp() throws Exception {
		//		 Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
	    
		zebraHelper = ZebraHelper.getInstance();
		ProcessDefinition pd = (ProcessDefinition) zebraHelper
				.getDefinitionFactory().getProcessDefinition("SimpleWorkflow");
		propertyGroups = (AntelopePropertyGroups) pd.getPropertyGroups();

	}

	public void testGetId() {
		assertTrue(propertyGroups.getId().longValue() > 0);
	}

	public void testGetPropertyElements() {
		Set propertySet = propertyGroups.getPropertyElements();
		assertFalse("No Property Elements", propertySet.isEmpty());
	}

}