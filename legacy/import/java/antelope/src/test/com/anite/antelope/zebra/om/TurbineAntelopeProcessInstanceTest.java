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

import java.util.List;
import java.util.Map;
import java.util.Set;

import junit.framework.TestCase;
import net.sf.hibernate.HibernateException;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.services.InitializationException;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.meercat.PersistenceException;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author martin.rouen
 *  
 */
public class TurbineAntelopeProcessInstanceTest extends TestCase {
	private AntelopeProcessInstance processInstance;

	//private Session session;
	private ZebraHelper zebraHelper;

	/*
	 * @see TestCase#setUp()
	 */
	protected void setUp() throws Exception {
		//session = PersistenceLocator.getInstance().getCurrentSession();
		// Initialise Fake Turbine so it can resolve Avalon
		TurbineTestCase.initialiseTurbine();
	    
		zebraHelper = ZebraHelper.getInstance();
		processInstance = zebraHelper.createProcessPaused("SimpleWorkflow");
	}

	public void testGetProcessDef() throws DefinitionNotFoundException {
		// IProcessDefinition processDefinition = this.processInstance
			//	.getProcessDef();
	}

	public void testGetProcessInstanceId() {
		Long processInstanceID = this.processInstance.getProcessInstanceId();
		assertTrue(processInstanceID.longValue() > 0);
	}

	public void testGetState() {
		long state = processInstance.getState();
		assertEquals(state, IProcessInstance.STATE_CREATED);
	}

	public void testGetTaskInstances() {
		Set taskInstances = processInstance.getTaskInstances();
		assertTrue("No Instances", taskInstances.isEmpty());

	}

	public void testGetParentProcessInstance() {
		//AntelopeProcessInstance parentProcess = processInstance
		//		.getParentProcessInstance();
		//ask about this. how to test?
	}

	

	public void testGetPropertySetEntryInstances() {
		Map propertySetEntryInstances = processInstance
				.getPropertySet();
		assertTrue("No Property Set Entry Instances",
				propertySetEntryInstances.isEmpty());

	}

	public void testGetProcessName() {
		String processName = processInstance.getProcessName();
		assertEquals("SimpleWorkflow", processName);
	}

	public void testGetActivatedBy() throws InitializationException, UnknownEntityException, DataBackendException, StateFailureException, ComponentException {
		UserManager userManager =  AvalonServiceHelper.instance().getSecurityService()
        .getUserManager();
		
		User antelope = userManager.getUser("Antelope");
		processInstance.setActivatedBy(antelope);		
		ZebraHelper.getInstance().getStateFactory().saveObject(processInstance);
		
		
		User activatedBy = processInstance.getActivatedBy();
		assertEquals(antelope.getName(), activatedBy.getName());
	}
	
	public void testRelatedClass() throws StateFailureException, ComponentException{
		processInstance.setRelatedClass(AntelopeTaskDefinition.class);
		processInstance.setRelatedKey(new Long(23));
		
		ITransaction t = ZebraHelper.getInstance().getStateFactory().beginTransaction();
		ZebraHelper.getInstance().getStateFactory().saveObject(processInstance);
		t.commit();
	}

	public void testGetHistoryInstances() {
		Set historyInstances = processInstance.getHistoryInstances();
		assertTrue(historyInstances.size() == 0);

	}

	public void testGetChildProcesses() throws PersistenceException,
			HibernateException, NestableException {
		List childProcesses = processInstance.getRunningChildProcesses();
		assertTrue("No ChildProcesses", childProcesses.isEmpty());
	}

	public void testGetParentTaskInstance() {
		ITaskInstance parentTaskInstance = processInstance
				.getParentTaskInstance();
		assertNull(parentTaskInstance);
			}

	public void testGetAllTasks() {
		//TODO GET ALL TASKS - NOT IN ORIG. CLASS?
	}

}