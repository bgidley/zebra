/*
 * Copyright 2004, 2005 Anite - Central Government Division
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

package com.anite.zebra.hivemind.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import org.apache.commons.logging.Log;
import org.hibernate.Session;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;
import com.anite.zebra.hivemind.api.LockManager;
import com.anite.zebra.hivemind.api.StateFactoryEvent;
import com.anite.zebra.hivemind.api.StateFactoryListener;
import com.anite.zebra.hivemind.api.ZebraStateFactory;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraFOE;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstanceHistory;

/**
 * Provides the state layer for the workflow engine
 * 
 * This does NOT inherit off the one in zebra-state as the one in state uses
 * Hibernate 2.1
 * 
 * @author Matthew.Norris
 * @author eric.pugh
 * @author Ben Gidley
 */
public class ZebraStateFactoryImpl implements IStateFactory, ZebraStateFactory {

    private List<StateFactoryListener> listeners = new ArrayList<StateFactoryListener>();
    
    private Session session;
    
	/**
	 * This should be manually injected by hivemind
	 */
	private LockManager lockManager;

	/**
	 * This should be automatically injected by hivemind
	 */
	private PriorityManager priorityManager;

	private Log log;

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#createFOE(com.anite.zebra.core.state.api.IProcessInstance)
     */
	public IFOE createFOE(IProcessInstance processInstance)
			throws CreateObjectException {
		return new ZebraFOE(processInstance);
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#deleteObject(com.anite.zebra.core.state.api.IStateObject)
     */
	public void deleteObject(IStateObject stateObject)
			throws StateFailureException {

		try {
			if (stateObject instanceof ZebraTaskInstance) {

				ZebraTaskInstance antelopeTaskInstance = (ZebraTaskInstance) stateObject;

				if (this.log.isInfoEnabled()) {
					produceDetailedDeleteLog(antelopeTaskInstance);
				}
				// Copy to history
				ZebraTaskInstanceHistory antelopeTaskInstanceHistory = new ZebraTaskInstanceHistory(
						antelopeTaskInstance);
				ZebraTaskDefinition taskDefinition = (ZebraTaskDefinition) antelopeTaskInstance
						.getTaskDefinition();
				antelopeTaskInstanceHistory.setShowInHistory(new Boolean(
						taskDefinition.getShowInHistory()));
				getSession().save(antelopeTaskInstanceHistory);

				// Tidy up process reference
				ZebraProcessInstance processInstance = (ZebraProcessInstance) antelopeTaskInstance
						.getProcessInstance();
				processInstance.getTaskInstances().remove(antelopeTaskInstance);
				antelopeTaskInstance.setProcessInstance(null);

				// Add history to processInstance
				processInstance.getHistoryInstances().add(
						antelopeTaskInstanceHistory);
				antelopeTaskInstanceHistory.setProcessInstance(processInstance);

				getSession().save(processInstance);
                
			}
			getSession().delete(stateObject);
		} catch (Exception e) {
			this.log.error("Failed to delete:" + stateObject.toString(), e);
			throw new StateFailureException("Failed to delete State Object", e);
		}

	}

	/**
	 * Helper to log a very detailed delete log for when things are acting oddly
	 * 
	 * @param antelopeTaskInstance
	 * @throws DefinitionNotFoundException
	 */
	private void produceDetailedDeleteLog(ZebraTaskInstance antelopeTaskInstance)
			throws DefinitionNotFoundException {
		ZebraTaskDefinition taskDef = (ZebraTaskDefinition) antelopeTaskInstance
				.getTaskDefinition();
		ZebraProcessInstance cpi = (ZebraProcessInstance) antelopeTaskInstance
				.getProcessInstance();
		ZebraProcessDefinition antelopeProcessDefinition = (ZebraProcessDefinition) cpi
				.getProcessDef();
		this.log
				.info("Creating history entry for task id "
						+ antelopeTaskInstance.getTaskInstanceId() + " def "
						+ antelopeProcessDefinition.getName() + "."
						+ taskDef.getName());
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#createProcessInstance(com.anite.zebra.core.definitions.api.IProcessDefinition)
     */
	public IProcessInstance createProcessInstance(
			IProcessDefinition processDefinition) throws CreateObjectException {

		ZebraProcessInstance processInstance = new ZebraProcessInstance();
		processInstance
				.setProcessName(((ZebraProcessDefinition) processDefinition)
						.getName());
		processInstance
				.setProcessDefinitionId(((ZebraProcessDefinition) processDefinition)
						.getId());

		return processInstance;
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#createTaskInstance(com.anite.zebra.core.definitions.api.ITaskDefinition, com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.state.api.IFOE)
     */
	public ITaskInstance createTaskInstance(ITaskDefinition taskDefinition,
			IProcessInstance processInstance, IFOE flowOfExecution)
			throws CreateObjectException {

		ZebraTaskInstance antelopeTaskInstance = new ZebraTaskInstance();
		ZebraProcessInstance antelopeProcessInstance = (ZebraProcessInstance) processInstance;
		ZebraTaskDefinition antelopeTaskDefinition = (ZebraTaskDefinition) taskDefinition;

		antelopeTaskInstance.setFOE(flowOfExecution);
		antelopeTaskInstance.setProcessInstance(antelopeProcessInstance);
		antelopeTaskInstance.setTaskDefinition(antelopeTaskDefinition);

		// Default values
		antelopeTaskInstance.setDateCreated(new Date());

		antelopeTaskInstance.setPriority(this.priorityManager
				.getDefaultPriority());
		antelopeTaskInstance.setCaption(antelopeTaskDefinition.getName());
		antelopeTaskInstance.setShowInTaskList(antelopeTaskDefinition
				.getShowInTaskList());
		antelopeProcessInstance.getTaskInstances().add(antelopeTaskInstance);

        // Fire event listeners
        StateFactoryEvent stateFactoryEvent = new StateFactoryEvent(this, antelopeTaskInstance);
        for (StateFactoryListener stateFactoryListener : listeners){
            stateFactoryListener.createTaskInstance(stateFactoryEvent);
        }
        
		return antelopeTaskInstance;
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#beginTransaction()
     */
	public ITransaction beginTransaction() throws StateFailureException {

		return new HibernateTransaction(getSession());

	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#saveObject(com.anite.zebra.core.state.api.IStateObject)
     */
	public void saveObject(IStateObject object) throws StateFailureException {
		getSession().saveOrUpdate(object);

	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#acquireLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
     */
	public void acquireLock(IProcessInstance processInstance, IEngine engine)
			throws LockException {

		this.lockManager.aquireLock(processInstance, getSession());

	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#releaseLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
     */
	public void releaseLock(IProcessInstance processInstance, IEngine engine)
			throws LockException {

		this.lockManager.releaseLock(processInstance, getSession());
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#getLockManager()
     */
	public LockManager getLockManager() {
		return this.lockManager;
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#setLockManager(com.anite.zebra.hivemind.api.LockManager)
     */
	public void setLockManager(LockManager lockManager) {
		this.lockManager = lockManager;
	}

	public Log getLog() {
		return this.log;
	}

	public void setLog(Log log) {
		this.log = log;
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#getPriorityManager()
     */
	public PriorityManager getPriorityManager() {
		return this.priorityManager;
	}

	/* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#setPriorityManager(com.anite.zebra.hivemind.impl.PriorityManager)
     */
	public void setPriorityManager(PriorityManager priorityManager) {
		this.priorityManager = priorityManager;
	}
    
    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#addStateFactoryListener(com.anite.zebra.hivemind.api.StateFactoryListener)
     */
    public void addStateFactoryListener(StateFactoryListener listener){
        listeners.add(listener);
    }
    
    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraStateFactory#removeStateFactoryListener(com.anite.zebra.hivemind.api.StateFactoryListener)
     */
    public void removeStateFactoryListener(StateFactoryListener listener){
        listeners.remove(listener);
    }

	public ZebraTaskInstance loadTaskInstance(Long taskInstanceId) {
		return (ZebraTaskInstance) getSession().load(ZebraTaskInstance.class, taskInstanceId);
	}

	public Session getSession() {
		return session;
	}

	public void setSession(Session session) {
		this.session = session;
	}

}