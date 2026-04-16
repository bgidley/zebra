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
public class TurbineAntelopePropertyElementTest extends TestCase {
	//private AntelopePropertyElement propertyElement;

	private ZebraHelper zebraHelper;

	private AntelopePropertyElement propertys;

	private AntelopePropertyGroups propertyGroups;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		//		 Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
	    
		zebraHelper = ZebraHelper.getInstance();
		ProcessDefinition pd = (ProcessDefinition) zebraHelper
				.getDefinitionFactory().getProcessDefinition("SimpleWorkflow");
		// group, key, value from over-ridden constructor
		propertyGroups = (AntelopePropertyGroups) pd.getPropertyGroups();
		Set propertySet = propertyGroups.getPropertyElements();
		propertys = (AntelopePropertyElement) propertySet.iterator().next();
		propertys.setValue("wibble");
	}

	/*
	 * Class under test for void AntelopePropertyElement(String, String, String)
	 */
	public void testAntelopePropertyElementStringStringString() {
		AntelopePropertyElement x = new AntelopePropertyElement("xGroup",
				"xKey", "xValue");
		assertEquals("Group doesnt match", "xGroup", x.getGroup());
		assertEquals("Key doesnt match", "xKey", x.getKey());
		assertEquals("Value doesnt math", "xValue", x.getValue());
	}

	/*
	 * Class under test for Long getId()
	 */
	public void testGetId() {
		assertNotNull(propertys.getId());
		assertTrue(propertys.getId().longValue() > 0);
	}

	/*
	 * Class under test for String getGroup()
	 */
	public void testGetGroup() {

		assertNotNull(propertys.getGroup());
		assertTrue(propertys.getGroup().length() > 0);
	}

	/*
	 * Class under test for String getKey()
	 */
	public void testGetKey() {
		assertNotNull(propertys.getKey());
		assertTrue(propertys.getKey().length() > 0);
	}

	/*
	 * Class under test for String getValue()
	 */
	public void testGetValue() {
		assertNotNull(propertys.getValue());
		assertTrue(propertys.getValue().length() > 0);
	}

}