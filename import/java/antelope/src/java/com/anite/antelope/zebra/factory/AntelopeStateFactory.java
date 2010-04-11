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

package com.anite.antelope.zebra.factory;

import java.util.Date;
import java.util.Iterator;

import net.sf.hibernate.Session;

import org.apache.avalon.framework.service.ServiceException;
import org.apache.avalon.framework.service.ServiceManager;
import org.apache.avalon.framework.service.Serviceable;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.managers.PriorityManager;
import com.anite.antelope.zebra.om.AntelopeFOE;
import com.anite.antelope.zebra.om.AntelopeLock;
import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstanceHistory;
import com.anite.antelope.zebra.processLifecycle.AntelopeTaskInstancePresets;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.ext.state.hibernate.HibernateStateFactory;
import com.anite.zebra.ext.state.hibernate.LockManager;

/**
 * Extends the standard HibernateStateFactory, only overriding methods where
 * CTMS's workflow objects need extra data. Retrives the session via the static
 * PersistenceLocator.
 * 
 * @author Matthew.Norris
 * @author eric.pugh
 * @author Ben Gidley
 */
public class AntelopeStateFactory extends HibernateStateFactory implements
        Serviceable {

    private LockManager lockManager = new NotClusterSafeLockManager();
    
    public LockManager getLockManager() {
        // TODO Auto-generated method stub
        return lockManager;
    }
    private static Log log = LogFactory.getLog(AntelopeStateFactory.class);

    private ServiceManager manager;

    /**
     * Provide Hibernate session via meercat persistance helper
     */
    public Session getSession() throws StateFailureException {
        try {
            return PersistenceLocator.getInstance().getCurrentSession();
        } catch (PersistenceException pe) {
            throw new StateFailureException(pe);
        }
    }

    public IFOE createFOE(IProcessInstance processInstance)
            throws CreateObjectException {
        return new AntelopeFOE(processInstance);
    }

    /**
     * Delete with extra step of creating a task instance history object
     */
    public void deleteObject(IStateObject stateObject)
            throws StateFailureException {

        Session s;
        try {
            s = PersistenceLocator.getInstance().getCurrentSession();

            if (stateObject instanceof AntelopeTaskInstance) {

                AntelopeTaskInstance antelopeTaskInstance = (AntelopeTaskInstance) stateObject;

                if (log.isInfoEnabled()) {
                    produceDetailedDeleteLog(antelopeTaskInstance);
                }
                // Copy to history
                AntelopeTaskInstanceHistory antelopeTaskInstanceHistory = new AntelopeTaskInstanceHistory(
                        antelopeTaskInstance);
                AntelopeTaskDefinition taskDefinition = (AntelopeTaskDefinition) antelopeTaskInstance
                        .getTaskDefinition();
                antelopeTaskInstanceHistory.setShowInHistory(new Boolean(
                        taskDefinition.getShowInHistory()));
                s.save(antelopeTaskInstanceHistory);

                // Tidy up process reference
                AntelopeProcessInstance processInstance = (AntelopeProcessInstance) antelopeTaskInstance
                        .getProcessInstance();
                processInstance.getTaskInstances().remove(antelopeTaskInstance);
                antelopeTaskInstance.setProcessInstance(null);

                // Add history to processInstance 
                processInstance.getHistoryInstances().add(
                        antelopeTaskInstanceHistory);
                antelopeTaskInstanceHistory.setProcessInstance(processInstance);

                s.save(processInstance);
            }
            s.delete(stateObject);
        } catch (Exception e) {
            log.error("Failed to delete:" + stateObject.toString(), e);
            throw new StateFailureException("Failed to delete State Object", e);
        }

    }

    /**
     * @param antelopeTaskInstance
     * @throws DefinitionNotFoundException
     */
    private void produceDetailedDeleteLog(
            AntelopeTaskInstance antelopeTaskInstance)
            throws DefinitionNotFoundException {
        AntelopeTaskDefinition taskDef = (AntelopeTaskDefinition) antelopeTaskInstance
                .getTaskDefinition();
        AntelopeProcessInstance cpi = (AntelopeProcessInstance) antelopeTaskInstance
                .getProcessInstance();
        AntelopeProcessDefinition antelopeProcessDefinition = (AntelopeProcessDefinition) cpi
                .getProcessDef();
        log
                .info("Creating history entry for task id "
                        + antelopeTaskInstance.getTaskInstanceId() + " def "
                        + antelopeProcessDefinition.getName() + "."
                        + taskDef.getName());
    }

    /**
     * Create a process and automatically set who did it
     */
    public IProcessInstance createProcessInstance(
            IProcessDefinition processDefinition) throws CreateObjectException {

        AntelopeProcessInstance processInstance = new AntelopeProcessInstance();
        processInstance
                .setProcessName(((AntelopeProcessDefinition) processDefinition)
                        .getName());
        processInstance
                .setProcessDefinitionId(((AntelopeProcessDefinition) processDefinition)
                        .getId());
        try {
            // processInstance.setActivatedBy(UserLocator.getLoggedInUser());
        } catch (Exception e) {
            log.error(e);
            throw new CreateObjectException(e);
        }
        return processInstance;
    }

    /**
     * Create a task and set properties
     */
    public ITaskInstance createTaskInstance(ITaskDefinition taskDefinition,
            IProcessInstance processInstance, IFOE flowOfExecution)
            throws CreateObjectException {

        AntelopeTaskInstance antelopeTaskInstance = new AntelopeTaskInstance();
        AntelopeProcessInstance antelopeProcessInstance = (AntelopeProcessInstance) processInstance;
        AntelopeTaskDefinition antelopeTaskDefinition = (AntelopeTaskDefinition) taskDefinition;

        antelopeTaskInstance.setFOE(flowOfExecution);
        antelopeTaskInstance.setProcessInstance(antelopeProcessInstance);
        antelopeTaskInstance.setTaskDefinition(antelopeTaskDefinition);

        AntelopeTaskInstancePresets presets = antelopeProcessInstance
                .getTaskDefinitionPresets(antelopeTaskDefinition);
        if (presets != null) {
            if (presets.getActualCompletionDate() != null) {
                antelopeTaskInstance.setActualCompletionDate(presets
                        .getActualCompletionDate());
            }
            if (presets.getCaption() != null) {
                antelopeTaskInstance.setCaption(presets.getCaption());
            } else {
                antelopeTaskInstance.setCaption(antelopeTaskDefinition
                        .getName());
            }
            if (presets.getDateCreated() != null) {
                antelopeTaskInstance.setDateCreated(presets.getDateCreated());
            } else {
                antelopeTaskInstance.setDateCreated(new Date());
            }
            if (presets.getDateDue() != null) {
                antelopeTaskInstance.setDateDue(presets.getDateDue());
            }
            if (presets.getDecisionMadeBy() != null) {
                antelopeTaskInstance.setDecisionMadeBy(presets
                        .getDecisionMadeBy());
            }
            if (presets.getDescription() != null) {
                antelopeTaskInstance.setDescription(presets.getDescription());
            }
            if (presets.getPriority() != null) {
                antelopeTaskInstance.setPriority(presets.getPriority());
            } else {
                antelopeTaskInstance.setPriority(PriorityManager.getInstance()
                        .getDefaultPriority());
            }
            if (presets.getTaskOwner() != null) {
                antelopeTaskInstance.setTaskOwner(presets.getTaskOwner());
            }
            
            if (presets.getPropertySet().size() > 0) {
                for (Iterator iter = presets.getPropertySet().keySet()
                        .iterator(); iter.hasNext();) {
                    String key = (String) iter.next();
                    antelopeTaskInstance.getPropertySet().put(key,
                            presets.getPropertySet().get(key));
                }
            }
        } else {
            // Default values
            antelopeTaskInstance.setDateCreated(new Date());

            antelopeTaskInstance.setPriority(PriorityManager.getInstance()
                    .getDefaultPriority());
            antelopeTaskInstance.setCaption(antelopeTaskDefinition.getName());
        }
        antelopeTaskInstance.setShowInTaskList(antelopeTaskDefinition
                .getShowInTaskList());
        
        antelopeProcessInstance.getTaskInstances().add(antelopeTaskInstance);

        return antelopeTaskInstance;
    }

    /**
     * Implementation specific function load object by ID Useful for storing
     * things in the HTTP session as ID and loading them on demand
     * 
     * @param clazz
     *            Type of object
     * @param id
     *            ID of object
     * @return The requested object
     * @throws StateFailureException
     */
    public IStateObject loadObject(Class clazz, Long id)
            throws StateFailureException {
        try {
            if (!clazz.equals(ITaskInstance.class)
                    || !clazz.equals(IProcessInstance.class)) {
                throw new StateFailureException("Unknown Class "
                        + clazz.getName());
            }
            return (IStateObject) getSession().load(clazz, id);

        } catch (Exception e) {
            throw new StateFailureException(
                    "Failed to load State Object with id " + id, e);
        }
    }

    /**
     * Tells parent to use AntelopeLock for locking
     */
    public Class getLockClass() {
        return AntelopeLock.class;
    }

    /**
     * Local service manger
     */
    public void service(ServiceManager manager) throws ServiceException {
        this.manager = manager;

    }
}