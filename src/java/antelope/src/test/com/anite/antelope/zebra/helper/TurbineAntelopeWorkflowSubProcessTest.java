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

package com.anite.antelope.zebra.helper;

import java.util.Iterator;

import junit.framework.TestCase;
import net.sf.hibernate.HibernateException;
import net.sf.hibernate.exception.NestableException;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstanceHistory;
import com.anite.meercat.PersistenceException;
import com.anite.zebra.core.exceptions.TransitionException;

/**
 * Run a workflow from End to end
 * @author John Rae
 */
public class TurbineAntelopeWorkflowSubProcessTest extends TestCase {

	private static final String PUSHSUBFLOW = "PushSubflow";
	private static Log log = LogFactory.getLog(TurbineAntelopeRunWorkflowTest.class);

	private static final String RUBBISH = "Rubbish";

	private static final String SPURIOUS = "Spurious";

	private static final String CHILD_CHANGE_PROPERTIES = "Child Change Properties";

	private static final String READ_PROPERTIES = "Child Read Properties";

	private static final String INITIALISE_SOME_PROPERTY = "Initialise Some Property";

	private static final String CHANGE_PROPERTIES = "Change Properties";

	private static final String DO_SOMETHING_ELSE = "Do something else";

	private static final String PARENT = "Parent";

	private static final String WOBBLE_VALUE = "Wobble Value";

	private static final String WOBBLE = "Wobble";

	private static final String WIBBLE = "Wibble";

	private static final String BOB = "Bob";

	private ZebraHelper zebraHelper;

	private AntelopeProcessInstance processInstance;

	private Iterator taskInstanceIterator;

	protected void setUp() throws Exception {
		
	    TurbineTestCase.initialiseTurbine();

		zebraHelper = ZebraHelper.getInstance();
	}

	/**
	 * @throws TransitionException
	 * @throws ComponentException
	 * @throws PersistenceException
	 * @throws HibernateException
	 * @throws NestableException
	 * @throws org.apache.commons.lang.exception.NestableException
	 * 
	 * This Test tests the Parent-Sub workflow. 
	 * Wobble and Spurious are set, (Wibble is set with a default value), 
	 * the flow goes into the subprocess where the values are checked
	 * Spurious should not be visible here
	 * Rubbish is created here but should not be visible outside
	 * Wibble's value is checked and put into Bob
	 * Wobble is checked and then has "edited" appended
	 * the subprocess is left
	 * at the end of the flow spurious is checked to make sure it isn't visible
	 * Wobble is checked to see that it has been changed
	 * Bob is checked to see that it contains Wibble's original value
	 * Wibble is checked to be null
	 * A value called "Gobbledigook" is checked to be null as it should be
	 */
	public void testRunWorkflowSubProcess() throws TransitionException, ComponentException, PersistenceException,
			HibernateException, NestableException, org.apache.commons.lang.exception.NestableException {
		log.debug("testing workflow Subprocess");
		//use parent
		//use sub within
		AntelopeTaskInstance task;
		AntelopePropertySetEntry antelopePropertySetEntry;

		processInstance = zebraHelper.createProcessPaused(PARENT);
		assertNotNull(processInstance);

		//get process instance
		zebraHelper.getEngine().startProcess(processInstance);

		
		//check first screen 
		task = checkTaskDef(INITIALISE_SOME_PROPERTY);
		//set values
		processInstance.getPropertySet().put(SPURIOUS, new AntelopePropertySetEntry(SPURIOUS));
		processInstance.getPropertySet().put(WOBBLE, new AntelopePropertySetEntry(WOBBLE_VALUE));
		transitionTask(task);

		//into subprocess
		task = checkTaskDef(READ_PROPERTIES, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));
		transitionTask(task, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));

		//next screen
		task = checkTaskDef(CHILD_CHANGE_PROPERTIES, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));
		//check no Spurious value exists
		assertNull(((AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0)).getPropertySet()
				.get(SPURIOUS));
		//enter Rubbish value
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(RUBBISH,
				new AntelopePropertySetEntry(RUBBISH));
		assertNotNull(((AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0)).getPropertySet()
				.get(RUBBISH));
		//get Wibble's value
		antelopePropertySetEntry = (AntelopePropertySetEntry) ((AntelopeProcessInstance) processInstance.getRunningChildProcesses()
				.get(0)).getPropertySet().get(WIBBLE);
		assertEquals(antelopePropertySetEntry.getValue(), "Moorhen");
		// and chuck it in Bob
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(BOB,
				antelopePropertySetEntry);
		//check Wobble while we're here
		antelopePropertySetEntry = (AntelopePropertySetEntry) ((AntelopeProcessInstance) processInstance.getRunningChildProcesses()
				.get(0)).getPropertySet().get(WOBBLE);
		assertEquals(antelopePropertySetEntry.getValue(), WOBBLE_VALUE);
		//then change it (adding edited to it's string value)
		AntelopePropertySetEntry newPropSetEntry = new AntelopePropertySetEntry(antelopePropertySetEntry.getValue()
				+ "edited");
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(WOBBLE, newPropSetEntry);
		transitionTask(task, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));

		//out of subprocess
		task = checkTaskDef(DO_SOMETHING_ELSE);
		//check that values Bob, Wibble & Spurious  are here, and Rubbish is not
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(BOB)).getValue(),
				"Moorhen");
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(WOBBLE)).getValue(),
				WOBBLE_VALUE + "edited");
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(SPURIOUS)).getValue(),
				SPURIOUS);
		assertNull(processInstance.getPropertySet().get(RUBBISH));
		//Check wibble is gone
		assertNull(processInstance.getPropertySet().get(WIBBLE));

		//Gobbledigook never mentioned before here
		assertNull(processInstance.getPropertySet().get("Gobbledigook"));
		transitionTask(task);

	}


	/**
	 * @throws TransitionException
	 * @throws ComponentException
	 * @throws PersistenceException
	 * @throws HibernateException
	 * @throws NestableException
	 * @throws org.apache.commons.lang.exception.NestableException
	 * 
	 * This Test tests the PushSubflow workflow.
	 * it tests the same things as the test for Parent except it has "push outputs" enabled
	 * this means that some tests which failed on the Parent test will pass here
	 *  
	 * Wobble and Spurious are set, (Wibble is set with a default value), 
	 * the flow goes into the subprocess where the values are checked
	 * Spurious should not be visible here
	 * Rubbish is created here but should not be visible outside
	 * Wibble's value is checked and put into Bob
	 * Wobble is checked and then has "edited" appended
	 * the subprocess is left
	 * at the end of the flow spurious is checked to make sure it isn't visible
	 * Wobble is checked to see that it has been changed
	 * Bob is checked to see that it contains Wibble's original value
	 * Wibble is checked to be null
	 * A value called "Gobbledigook" is checked to be null as it should be
	 */

	public void testRunWorkflowPushSubProcess() throws TransitionException, ComponentException, PersistenceException,
			HibernateException, NestableException, org.apache.commons.lang.exception.NestableException {
		log.debug("testing workflow Subprocess");
		//use parent
		//use sub within
		AntelopeTaskInstance task;
		AntelopePropertySetEntry antelopePropertySetEntry;

		processInstance = zebraHelper.createProcessPaused(PUSHSUBFLOW);
		assertNotNull(processInstance);

		//get process instance
		zebraHelper.getEngine().startProcess(processInstance);

		//check first screen 
		task = checkTaskDef(INITIALISE_SOME_PROPERTY);
		//set values
		processInstance.getPropertySet().put(SPURIOUS, new AntelopePropertySetEntry(SPURIOUS));
		processInstance.getPropertySet().put(WOBBLE, new AntelopePropertySetEntry(WOBBLE_VALUE));
		transitionTask(task);

		//into subprocess
		task = checkTaskDef(READ_PROPERTIES, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));
		transitionTask(task, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));

		//next screen
		task = checkTaskDef(CHILD_CHANGE_PROPERTIES, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));
		//check no Spurious value exists
		assertNull(((AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0)).getPropertySet()
				.get(SPURIOUS));
		//enter Rubbish value
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(RUBBISH,
				new AntelopePropertySetEntry(RUBBISH));
		assertNotNull(((AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0)).getPropertySet()
				.get(RUBBISH));
		//get Wibble's value
		antelopePropertySetEntry = (AntelopePropertySetEntry) ((AntelopeProcessInstance) processInstance.getRunningChildProcesses()
				.get(0)).getPropertySet().get(WIBBLE);
		assertEquals(antelopePropertySetEntry.getValue(), "Moorhen");
		// and chuck it in Bob
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(BOB,
				antelopePropertySetEntry);
		//check Wobble while we're here
		antelopePropertySetEntry = (AntelopePropertySetEntry) ((AntelopeProcessInstance) processInstance.getRunningChildProcesses()
				.get(0)).getPropertySet().get(WOBBLE);
		assertEquals(antelopePropertySetEntry.getValue(), WOBBLE_VALUE);
		//then change it (adding edited to it's string value)
		AntelopePropertySetEntry newPropSetEntry = new AntelopePropertySetEntry(antelopePropertySetEntry.getValue()
				+ "edited");
		((AntelopeProcessInstance) task.getProcessInstance()).getPropertySet().put(WOBBLE, newPropSetEntry);
		transitionTask(task, (AntelopeProcessInstance) processInstance.getRunningChildProcesses().get(0));

		//out of subprocess
		task = checkTaskDef(DO_SOMETHING_ELSE);
		//check that values Bob, Wibble & Spurious  are here, and Rubbish is not
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(BOB)).getValue(),
				"Moorhen");
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(WOBBLE)).getValue(),
				WOBBLE_VALUE + "edited");
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(SPURIOUS)).getValue(),
				SPURIOUS);
		
		//***********these are the only two lines that are different from the check on Parent********************
		//***********they show that the Rubbish value and Wibble are still available after the Subprocess********
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(RUBBISH)).getValue(),
				RUBBISH);
		assertEquals(((AntelopePropertySetEntry) processInstance.getPropertySet().get(WIBBLE)).getValue(),
				"Moorhen");

		//Gobbledigook never mentioned before here
		assertNull(processInstance.getPropertySet().get("Gobbledigook"));
		transitionTask(task);

		//use pushSubflow
		//use sub

	}

	/**
	 * @param task
	 * @throws TransitionException
	 * @throws ComponentException
	 */
	private void transitionTask(AntelopeTaskInstance task, AntelopeProcessInstance antelopeProcessInstance)
			throws TransitionException, ComponentException {
		log.debug("transitioning task");
		//goto next task
		zebraHelper.getEngine().transitionTask(task);
		boolean found = false;
		for (Iterator iter = antelopeProcessInstance.getHistoryInstances().iterator(); iter.hasNext();) {
			AntelopeTaskInstanceHistory element = (AntelopeTaskInstanceHistory) iter.next();
			String elementName = ((AntelopeTaskDefinition) element.getTaskDefinition()).getName();
			String taskName = ((AntelopeTaskDefinition) task.getTaskDefinition()).getName();
			if (elementName.equals(taskName))
				found = true;
		}

		assertTrue(found);

	}

	private void transitionTask(AntelopeTaskInstance task) throws TransitionException, ComponentException {
		transitionTask(task, processInstance);
	}

	/**
	 * @param taskName
	 * @throws TransitionException
	 * @throws ComponentException
	 * 
	 * tests Task Definitions
	 */
	private AntelopeTaskInstance checkTaskDef(String taskName, AntelopeProcessInstance antelopeProcessInstance)
			throws TransitionException, ComponentException {
		log.debug("testing task");
		//get process
		//check correct process
		//advance flow
		assertEquals(antelopeProcessInstance.getTaskInstances().size(), 1);
		taskInstanceIterator = antelopeProcessInstance.getTaskInstances().iterator();
		AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator.next();
		assertNotNull(task);
		assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition()).getName(), taskName);
		return task;
		//zebraHelper.getEngine().transitionTask(task);//do this externally now
	}

	private AntelopeTaskInstance checkTaskDef(String taskName) throws TransitionException, ComponentException {
		return checkTaskDef(taskName, processInstance);
	}

}

