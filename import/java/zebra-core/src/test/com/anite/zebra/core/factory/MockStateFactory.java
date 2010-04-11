package com.anite.zebra.core.factory;
/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

import junit.framework.Assert;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockTransaction;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.MockFOE;
import com.anite.zebra.core.state.MockProcessInstance;
import com.anite.zebra.core.state.MockTaskInstance;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Eric Pugh
 * @author Matthew Norris
 */
public class MockStateFactory implements IStateFactory {

	private Set audit = new HashSet();

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#beginTransaction()
	 */
	public ITransaction beginTransaction() throws StateFailureException {
		return new MockTransaction();
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#saveObject(com.anite.zebra.core.state.api.IStateObject)
	 */
	public void saveObject(IStateObject aso) throws StateFailureException {		

	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#deleteObject(com.anite.zebra.core.state.api.IStateObject)
	 */
	public void deleteObject(IStateObject so) throws StateFailureException {
		if (so instanceof MockTaskInstance){
			Assert.assertTrue(audit.contains(so));
			MockTaskInstance taskInstance = (MockTaskInstance)so;
			Assert.assertTrue(taskInstance.getState()==ITaskInstance.STATE_COMPLETE);
			Assert.assertTrue(taskInstance.getProcessInstance().getTaskInstances().contains(taskInstance));
			taskInstance.getProcessInstance().getTaskInstances().remove(taskInstance);
			Assert.assertFalse(taskInstance.getProcessInstance().getTaskInstances().contains(taskInstance));
			taskInstance.setState(MockTaskInstance.STATE_DELETED);
			
		} else if (so instanceof MockProcessInstance) {
			Assert.assertTrue(audit.contains(so));
			MockProcessInstance pi = (MockProcessInstance) so;
			pi.setState(MockProcessInstance.STATE_DELETED);
			
		} else {
			Assert.fail("Unknown class " + so);
		}
		
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#createProcessInstance(com.anite.zebra.core.definitions.api.IProcessDefinition)
	 */
	public IProcessInstance createProcessInstance(IProcessDefinition processDef)
			throws CreateObjectException {
		MockProcessInstance pi = new MockProcessInstance(processDef); 
		audit.add(pi);
		return pi;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#createTaskInstance(com.anite.zebra.core.definitions.api.ITaskDefintions, com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.state.api.IFOE)
	 */
	public ITaskInstance createTaskInstance(ITaskDefinition taskDef,
			IProcessInstance processInstance, IFOE foe)
			throws CreateObjectException {
		ITaskInstance taskInstance =  new MockTaskInstance(taskDef,(MockProcessInstance) processInstance,foe);
		processInstance.getTaskInstances().add(taskInstance);
		audit.add(taskInstance);
		return taskInstance;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#createFOE(com.anite.zebra.core.state.api.IProcessInstance)
	 */
	public IFOE createFOE(IProcessInstance processInstance)
			throws CreateObjectException {
		MockFOE foe = new MockFOE(processInstance);
		this.audit.add(foe);
		return foe;
	}

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#acquireLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
     */
    public void acquireLock(IProcessInstance processInstance, IEngine engine) throws LockException {
    	// quick and dirty locking mechanism
    	MockProcessInstance pi = (MockProcessInstance) processInstance;
    	while (pi.isLocked()) {
    		try {
				Thread.sleep(100);
			} catch (InterruptedException e) {
				throw new LockException("Thread sleep whilst waiting for lock interrupted!");
			}
    	}
    	pi.setLocked(true);
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#releaseLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
     */
    public void releaseLock(IProcessInstance processInstance, IEngine engine) throws LockException {
    	MockProcessInstance pi = (MockProcessInstance) processInstance;
    	if (!pi.isLocked()) {
    		throw new LockException("Process isn't marked as Locked!");
    	}
    	pi.setLocked(false);
    }
    
    public Set getAuditTrail() {
    	return audit;
    }
    
    public void resetAuditTrail() {
    	this.audit = new HashSet();
    }
    
    /**
     * 
     * allows you to specific a Set for the audittrail to use. 
     * useful if you have multiple instances of the factory pointing at 
     * a single data store (simulates multiple state factories pointing at 
     * the same database) 
     * 
     * @param auditTrail
     *
     * @author Matthew.Norris
     * Created on 22-Sep-2005
     */
    public void setAuditTrail(Set auditTrail) {
    	if (auditTrail==null) {
    		throw new RuntimeException("Cannot set audit trail to NULL");
    	}
    	this.audit = auditTrail;
    }
    /**
     * returns a count of the number of instances of a definition (process or task) exists
     * in the audit trail
     * 
     * @author Matthew Norris
     * Created on 19-Aug-2005
     *
     * @param definitionToCount
     * @return
     * @throws DefinitionNotFoundException 
     */
    public int countInstances(MockProcessDef processDef) throws DefinitionNotFoundException {
    	int x = 0;
    	for (Iterator it = audit.iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockProcessInstance) {
    			MockProcessInstance pi = (MockProcessInstance) o;
    			if (pi.getProcessDef().equals(processDef)) {
    				x++;
    			}
    		}
    	}
		return x;
    }
    /**
     * returns a count of the task instances 
	 * that match the task definition 
	 * specified
	 * @param taskDef
     * @return
     * @throws DefinitionNotFoundException
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public int countInstances(MockTaskDef taskDef) throws DefinitionNotFoundException {
    	int x = 0;
    	for (Iterator it = audit.iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockTaskInstance) {
    			MockTaskInstance ti = (MockTaskInstance) o;
    			if (ti.getTaskDefinition().equals(taskDef)) {
    				x++;
    			}
    		}
    	}
		return x;
    }
    
    /**
     * returns a count of the task instances 
     * that match the task definition and task instance state
	 * specified
	 * @param taskDef
     * @param expectedState
     * @return
     * @throws DefinitionNotFoundException
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public int countInstances(MockTaskDef taskDef, long expectedState) throws DefinitionNotFoundException {
    	int x = 0;
    	for (Iterator it = audit.iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockTaskInstance) {
    			MockTaskInstance ti = (MockTaskInstance) o;
    			if (ti.getTaskDefinition().equals(taskDef)) {
    				if(ti.getState()==expectedState) {
    					x++;
    				}
    			}
    		}
    	}
		return x;
    }
    
    /**
     * returns a count of FOE objects for the specified process instance
     * 
     * @param pi
     * @return
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public int countFOE(IProcessInstance pi) {
    	int x = 0;
    	for (Iterator it = getFOEs(pi).iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockFOE) {
				x++;
    		}
    	}    	
    	return x;
    }
    
    /**
     * returns a count of the number of task instances
     * associated with this FOE
     * 
     * @param foe
     * @return
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public int countFOETasks(MockFOE foe) {
    	int x = 0;
    	for (Iterator it = audit.iterator();it.hasNext();) {
    		Object o = it.next();
    		if (o instanceof MockTaskInstance) {
    			MockTaskInstance ti = (MockTaskInstance) o;
    			if(ti.getFOE().equals(foe)) {
    				x++;
    			}
    		}
    	}    	
    	return x;
    	
    }
    
    /**
     * 
     * returns the FOE objects associated with a 
     * processinstance that ran a given task definition
     * @param pi
     * @param td
     * @return
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     * @throws DefinitionNotFoundException 
     */
    public Set getFOEs(IProcessInstance pi, ITaskDefinition td) throws DefinitionNotFoundException {
    	Set foes = new HashSet();
    	for (Iterator it = this.audit.iterator();it.hasNext();) {
    		IStateObject o = (IStateObject) it.next();
    		if (o instanceof MockTaskInstance) {
    			MockTaskInstance ti = (MockTaskInstance) o;
    			if (ti.getTaskDefinition().equals(td) &&  ti.getProcessInstance().equals(pi) && !foes.contains(ti.getFOE())) {
    				foes.add(ti.getFOE());
    			}
    		}
    	}
    	return foes;
    }
    /**
     * returns the FOEs associated with the processinstance
     * @param pi
     * @return
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public Set getFOEs(IProcessInstance pi) {
    	Set foes = new HashSet();
    	for (Iterator it = this.audit.iterator();it.hasNext();) {
    		IStateObject o = (IStateObject) it.next();
    		if (o instanceof MockFOE) {
    			MockFOE foe = (MockFOE) o;
    			if (foe.getProcessInstance().equals(pi) && !foes.contains(foe)) {
    				foes.add(foe);
    			}
    		}
    	}
    	return foes;
    }
    
    /**
     * 
     * the task instances that belong to the specified
     * process instance that are of the specified 
     * task definition
     * @param pi
     * @param td
     * @return
     * @throws DefinitionNotFoundException
     *
     * @author Matthew.Norris
     * Created on Sep 25, 2005
     */
    public Set getTaskInstances(IProcessInstance pi, ITaskDefinition td) throws DefinitionNotFoundException {
    	Set tasks =  new HashSet();
    	for (Iterator it = audit.iterator();it.hasNext();) {
    		IStateObject o = (IStateObject) it.next();
    		if ( o instanceof ITaskInstance) {
				ITaskInstance ti = (ITaskInstance) o;
				if (ti.getProcessInstance().equals(pi)) {
					if (ti.getTaskDefinition().equals(td)) {
						tasks.add(ti);
					}
				}
			}
    	}
    	return tasks;
    }
}
