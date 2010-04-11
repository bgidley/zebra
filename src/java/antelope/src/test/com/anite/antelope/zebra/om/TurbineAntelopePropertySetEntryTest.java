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

import java.util.Date;
import java.util.Map;

import junit.framework.TestCase;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.helper.ZebraHelper;

/**
 * @author martin.rouen
 */
public class TurbineAntelopePropertySetEntryTest extends TestCase {
	//test processInstance
	// value and/or Object
	//looking for value bit of the key/value pair
	private AntelopePropertySetEntry propertySetEntry;

	private ZebraHelper zebraHelper;

	private AntelopeProcessInstance processInstance;

	private Map propertySetInstance;

	protected void setUp() throws Exception {
		//		 Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
	    
		zebraHelper = ZebraHelper.getInstance();
		processInstance = zebraHelper.createProcessPaused("SimpleWorkflow");
		propertySetInstance = processInstance.getPropertySet();
	}

	public void testAntelopePropertySetEntry() {

	}

	public void testAntelopePropertySetEntryString() {
		AntelopePropertySetEntry x = new AntelopePropertySetEntry("set entry");
		assertEquals("set entry", x.getValue());
	}

	public void testAntelopePropertySetEntryObject() {
		Date d = new Date();
		AntelopePropertySetEntry y = new AntelopePropertySetEntry(d);
		assertEquals(y.getObject(), d);
	}

	public void testGetId() {
		Integer ii = new Integer(211);
		AntelopePropertySetEntry iid = new AntelopePropertySetEntry();
		iid.setId(ii);
		assertEquals(ii, iid.getId());
	}

	//public void testSetId() {
	//}

	public void testGetValue() {

		AntelopePropertySetEntry vValue = new AntelopePropertySetEntry();
		vValue.setValue("Value is set");
		assertEquals("Value is set", vValue.getValue());
	}

	//public void testSetValue() {
	//}

	public void testGetObject() {
		Date d = new Date();
		AntelopePropertySetEntry oObject = new AntelopePropertySetEntry();
		oObject.setObject(d);
		assertEquals(d, oObject.getObject());

	}

	//public void testSetObject() {
	//}

}