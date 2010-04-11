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

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.Stack;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Query;
import net.sf.hibernate.Session;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.services.InitializationException;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.processLifecycle.AntelopeTaskInstancePresets;
import com.anite.antelope.zebra.processLifecycle.ProcessDestruct;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * Extends Process Instance to set XDoclet tags and custom properties
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 * @hibernate.class lazy="true"
 * @hibernate.query name="tasks" query="from AntelopeTaskInstance ati where ati.processInstance = :processInstance and ati.showInTaskList=:showInTaskList"
 * @hibernate.cache usage="transactional"
 */
public class AntelopeProcessInstance implements IProcessInstance {

    private static final String TASKPRESET = "TaskPreset";

    private static final String ZEBRA_PERMISSION_PREFIX = "ZEBRA";

    private static Log log = LogFactory.getLog(AntelopeProcessInstance.class);

    /* Field Variables for Interface */
    private Long processDefinitionId;

    private Long processInstanceId = null;

    private long state;

    private Set taskInstances = new HashSet();

    /* Custom behavioural properties */
    /** Parent Process used for subflows */
    private AntelopeProcessInstance parentProcessInstance;

    /** Task instance from parent for subflow step */
    private ITaskInstance parentTaskInstance;

    /* Custom Informational Properties */
    /** The user friendly name of this process */
    private String processName;

    /** The user that activated this process */
    private User activatedBy;

    /** The property set catch all for anything at all */
    private Map propertySet = new HashMap();

    /** Set of historical process information */
    private Set historyInstances = new HashSet();

    /**
     * Maps dynamic permission names to fulcrum security permission names
     */
    private Map dynamicPermissionMap = new HashMap();

    /**
     * If this is linked to an data entity its class goes here
     */
    private Class relatedClass = null;

    /**
     * If this is linked to a data entity its key goes here
     */
    private Long relatedKey = null;

    /**
     * Set of FOE's need to make sure they are deleted with process
     */
    private Set fOES = new HashSet();

    /**
     * Default constructor for normal construction
     */
    public AntelopeProcessInstance() {

    }

    /**
     * constructor from another instance (e.g. for history)
     * 
     * @param processInstance
     *            AntelopeProcessInstance
     */
    public AntelopeProcessInstance(AntelopeProcessInstance processInstance)
            throws NestableException {
        if (processInstance == null) {
            throw new NestableException(
                    "Cannot instantiate AntelopeProcessInstance class without a valid AntelopeProcessInstance object");
        }
    }

    /* IProcessInstance Methods */

    /**
     * Interface method for get the Process definition Note this should never
     * actually throw definition not found exception
     */
    public IProcessDefinition getProcessDef()
            throws DefinitionNotFoundException {

        try {
            return ZebraHelper.getInstance().getDefinitionFactory()
                    .getProcessDefinition(processDefinitionId);
        } catch (DefinitionNotFoundException e) {
            log.error("", e);
            throw e;
        } catch (ComponentException e) {
            log.error("Could not get definitions factory", e);
            throw new DefinitionNotFoundException(e);
        }
    }

    /**
     * @return Returns the processInstanceId.
     * @hibernate.id generator-class="native"
     */
    public Long getProcessInstanceId() {
        return processInstanceId;
    }

    /**
     * @param processInstanceId
     *            The processInstanceId to set.
     */
    public void setProcessInstanceId(Long processInstanceId) {
        this.processInstanceId = processInstanceId;
    }

    /**
     * @hibernate.property
     */
    public long getState() {
        return state;
    }

    public void setState(long newState) {
        this.state = newState;
    }

    /**
     * @hibernate.set cascade="all" lazy="true" inverse="true"
     * @hibernate.collection-key column="processInstanceId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeTaskInstance"
     * @hibernate.collection-cache usage="transactional"
     * @return
     */
    public Set getTaskInstances() {
        return this.taskInstances;
    }

    public void setTaskInstances(Set taskInstances) {
        this.taskInstances = taskInstances;
    }

    /* Implementation Methods */

    /**
     * @hibernate.many-to-one cascade="none" not-null="false"
     * @return Returns the parentProcessInstance.
     */
    public AntelopeProcessInstance getParentProcessInstance() {
        return parentProcessInstance;
    }

    /**
     * @param parentProcessInstance
     *            The parentProcessInstance to set.
     */
    public void setParentProcessInstance(
            AntelopeProcessInstance parentProcessInstance) {
        this.parentProcessInstance = parentProcessInstance;
    }

    /**
     * @return Returns the processDefinition.
     * @throws DefinitionNotFoundException
     */
    public AntelopeProcessDefinition getProcessDefinition()
            throws DefinitionNotFoundException {
        return (AntelopeProcessDefinition) this.getProcessDef();
    }

    /**
     * @hibernate.map cascade="all" lazy="true"
     * @hibernate.collection-index column="propertyKey" type="string"
     * @hibernate.collection-key column="processInstanceId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopePropertySetEntry"
     * @hibernate.collection-cache usage="transactional"
     * @return
     */
    public Map getPropertySet() {
        return this.propertySet;
    }

    public void setPropertySet(Map propertySetEntries) {
        this.propertySet = propertySetEntries;
    }

    /**
     * @hibernate.property not-null="true"
     * @return Returns the processName.
     */
    public String getProcessName() {
        return processName;
    }

    /**
     * @param processName
     *            The processName to set.
     */
    public void setProcessName(String processName) {
        this.processName = processName;
    }

    /**
     * @hibernate.many-to-one cascade="save-update" not-null="false"
     *                        class="org.apache.fulcrum.security.model.dynamic.entity.DynamicUser"
     * 
     * @return
     */
    public User getActivatedBy() {
        return activatedBy;
    }

    public void setActivatedBy(User activatedBy) {
        this.activatedBy = activatedBy;
    }

    /**
     * @hibernate.set cascade="all" lazy="true" inverse="true"
     * @hibernate.collection-key column="processInstanceId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeTaskInstanceHistory"
     * @hibernate.collection-cache usage="transactional"
     * @return
     */
    public Set getHistoryInstances() {
        return this.historyInstances;
    }

    /**
     * @hibernate.many-to-one cascade="none" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopeTaskInstance"
     * @return Returns the parentTaskInstance. (Null if this is not a
     *         subprocess)
     */
    public ITaskInstance getParentTaskInstance() {
        return parentTaskInstance;
    }

    public void setHistoryInstances(Set historyInstances) {
        this.historyInstances = historyInstances;
    }

    /**
     * returns a recursive list of processes that are children of this process
     * 
     * @return list of processes that are children of this process
     * @throws PersistenceException
     *             persistence exception
     * @throws HibernateException
     *             hibernate exception
     */
    public List getRunningChildProcesses() throws PersistenceException,
            HibernateException, NestableException {

        List results = new ArrayList();

        String querySQL = "select api from AntelopeProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";
        querySQL += " and api.state=:state";

        Session s = PersistenceLocator.getInstance().getCurrentSession();
        Query q = s.createQuery(querySQL);
        q.setCacheable(true);
        q.setLong("state", IProcessInstance.STATE_RUNNING);

        // Recursive Process children
        recursivelyQueryChildProcesses(results, q);
        return results;
    }

    public List getRunningRelatedProcesses() throws PersistenceException,
            HibernateException {

        if (this.getRelatedKey() != null) {

            String querySQL = "select api from AntelopeProcessInstance api where api.relatedClass =:relatedClass";
            querySQL += " and api.relatedKey = :relatedKey";
            querySQL += " and api.state=:state";

            Session s = PersistenceLocator.getInstance().getCurrentSession();
            Query q = s.createQuery(querySQL);
            q.setCacheable(true);
            q.setParameter("relatedClass", this.getRelatedClass());
            q.setLong("relatedKey", this.getRelatedKey().longValue());
            q.setLong("state", IProcessInstance.STATE_RUNNING);
            return q.list();
        }
        List results = new ArrayList();
        return results;
    }

    /**
     * Returns a list of all related processes that are complete
     * 
     * @return list of processes that are children of this process
     * @throws PersistenceException
     *             persistence exception
     * @throws HibernateException
     *             hibernate exception
     */
    public List getCompleteRelatedProcesses() throws PersistenceException,
            HibernateException, NestableException {

        if (this.getRelatedKey() != null) {

            String querySQL = "select api from AntelopeProcessInstance api where api.relatedClass =:relatedClass";
            querySQL += " and api.relatedKey = :relatedKey";
            querySQL += " and api.state=:state";

            Session s = PersistenceLocator.getInstance().getCurrentSession();
            Query q = s.createQuery(querySQL);
            q.setCacheable(true);
            q.setParameter("relatedClass", this.getRelatedClass());
            q.setParameter("relatedKey", this.getRelatedKey());
            q.setLong("state", IProcessInstance.STATE_COMPLETE);

            return q.list();
        }
        return new ArrayList();
    }

    /**
     * Get all child processes not running (e.g. complete and killed)
     * @return
     * @throws PersistenceException
     * @throws HibernateException
     */
    public List getNotRunningChildProcesses() throws PersistenceException,
            HibernateException {
        List results = new ArrayList();

        String querySQL = "select api from AntelopeProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";
        querySQL += " and api.state!=:state";

        Session s = PersistenceLocator.getInstance().getCurrentSession();
        Query q = s.createQuery(querySQL);
        q.setLong("state", IProcessInstance.STATE_RUNNING);
        q.setCacheable(true);

        recursivelyQueryChildProcesses(results, q);
        return results;
    }

    /**
     * @param results
     * @param q
     * @throws HibernateException
     */
    private void recursivelyQueryChildProcesses(List results, Query q)
            throws HibernateException {
        // Recursive Process children
        Stack checkList = new Stack();
        checkList.push(this);
        while (!checkList.isEmpty()) {
            AntelopeProcessInstance processInstance = (AntelopeProcessInstance) checkList
                    .pop();
            q.setLong("guid", processInstance.getProcessInstanceId()
                    .longValue());
            for (Iterator it = q.iterate(); it.hasNext();) {
                AntelopeProcessInstance childProcess = (AntelopeProcessInstance) it
                        .next();
                results.add(childProcess);
                checkList.push(childProcess);
            }
        }
    }

    /**
     * Get all child processes regardless of state
     * @return
     * @throws PersistenceException
     * @throws HibernateException
     */
    public List getAllChildProcesses() throws PersistenceException,
            HibernateException {
        List results = new ArrayList();

        String querySQL = "select api from AntelopeProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";

        Session s = PersistenceLocator.getInstance().getCurrentSession();
        Query q = s.createQuery(querySQL);
        q.setCacheable(true);

        // Recursive Process children
        recursivelyQueryChildProcesses(results, q);
        return results;
    }

    /**
     * @param parentTaskInstance
     *            The parentTaskInstance to set.
     */
    public void setParentTaskInstance(ITaskInstance parentTaskInstance) {
        this.parentTaskInstance = parentTaskInstance;
    }

    /**
     * returns a list of all available tasks for the current user on this
     * process
     * 
     * @return list of all available tasks for the current user on this process
     * @throws HibernateException
     */
    public List getUsersTasks() throws NestableException, HibernateException {

        Session session = PersistenceLocator.getInstance().getCurrentSession();
        Query tasks = session.getNamedQuery("tasks");
        tasks.setParameter("processInstance", this);
        tasks.setParameter("showInTaskList", Boolean.TRUE);

        return tasks.list();
    }

    /* Helper functions to help with finding tasks */

    /**
     * Looks for the first list of tasks that come from the child(ren) of this
     * processinstance This is used for finding the next screen. We don't do
     * this exaustively as it could be very large. The first is good enough for
     * determining the next screen
     */
    public List getFirstTasksFromAChildProcess() throws NestableException {

        Stack checkList = new Stack();
        checkList.push(this);
        while (!checkList.isEmpty()) {
            try {
                AntelopeProcessInstance currentProcess = (AntelopeProcessInstance) checkList
                        .pop();
                List childProcesses = currentProcess.getRunningChildProcesses();
                for (Iterator it = childProcesses.iterator(); it.hasNext();) {
                    AntelopeProcessInstance child = (AntelopeProcessInstance) it
                            .next();
                    List allTasks = child.getUsersTasks();
                    if (!allTasks.isEmpty()) {
                        return allTasks;
                    }
                    checkList.push(child);
                }
            } catch (Exception e) {
                String emsg = "Failed to retrieve child processes";
                log.error(emsg, e);
                throw new NestableException(emsg, e);
            }
        }
        return new ArrayList();
    }

    /**
     * looks for tasks from the parent(s) of the processInstance
     * 
     * @return
     */
    public List getFirstTasksFromAParentProcess() throws NestableException {
        AntelopeProcessInstance parentInstance = null;
        try {
            parentInstance = this.getParentProcessInstance();
            while (parentInstance != null) {
                if (log.isInfoEnabled()) {
                    log.info("Getting tasks for parent process  "
                            + this.getProcessInstanceId());
                }
                // get parent tasks
                List allTasks = parentInstance.getUsersTasks();

                if (!allTasks.isEmpty()) {
                    return allTasks;
                }
                parentInstance = parentInstance.getParentProcessInstance();
            }
        } catch (Exception e) {
            String emsg = "Problem accessing parent process tasks";
            log.error(emsg, e);
            throw new NestableException(emsg, e);
        }
        return new ArrayList();
    }

    /**
     * Determine the next task with a screen to run Return null is inderminate
     */
    public AntelopeTaskInstance determineNextScreenTask()
            throws HibernateException, NestableException {

        List taskList = this.getUsersTasks();

        AntelopeTaskInstance taskInstance = null;

        if (taskList.isEmpty()) {
            taskList = this.getFirstTasksFromAChildProcess();
        }

        if (taskList.isEmpty()) {
            taskList = this.getFirstTasksFromAParentProcess();
        }

        if (taskList.size() == 1) {
            taskInstance = (AntelopeTaskInstance) taskList.get(0);

            String screenName = ((AntelopeTaskDefinition) taskInstance
                    .getTaskDefinition()).getScreenName();
            if (screenName != null) {
                return taskInstance;
            }
        }
        return null;
    }

    /**
     * Gets the fulcrum permission object for a dynamic permission name
     * 
     * @param permissionNames
     * @return @throws
     *         NestableException
     */
    public PermissionSet getDynamicPermissions(String permissionNames)
            throws NestableException {
        if (permissionNames != null) {

            String[] actualPermissionNames = permissionNames.split(";");

            for (int i = 0; i < actualPermissionNames.length; i++) {
                actualPermissionNames[i] = getDynamicPermission(actualPermissionNames[i]);
            }

            return ZebraHelper.getInstance().getPermissionSet(
                    actualPermissionNames);
        }
        return new PermissionSet();
    }

    /**
     * Gets the actual permission for passed dynamic perission name
     * 
     * If you want to grant a user a dynamic permission call this function
     * to find out what permission to grant.
     * 
     * If on the other hand you want to link an existing permission to a dynamic
     * permission named call registerDynamicPermission
     * 
     * @param permissionName
     * @return
     * @throws NestableException
     */
    public String getDynamicPermission(String permissionName)
            throws NestableException {
        if (permissionName != null) {

            if (!this.getDynamicPermissionMap().containsKey(permissionName)) {
                // Otherwise bind permision to related class/ourselves
                String suffix = this.getSuffix();
                String actualPermissionName = ZEBRA_PERMISSION_PREFIX
                        + permissionName + "[" + suffix + "]";

                // check permission exists if not create it
                Permission permission = ZebraHelper.getInstance()
                        .loadOrCreatePermission(actualPermissionName);

                // add to dynamic map
                this.registerDynamicPermission(permissionName, permission);

            }
            // first look in the map
            return (String) this.getDynamicPermissionMap().get(permissionName);
        }
        return null;
    }

    /**
     * Call this to register a fulcrum permission to a an dynamic permission name
     * From this point onwards that dynamic permissionName will satify the workflow
     * engine
     * 
     * If called for a permission already registered it is replaced.
     * 
     * This only needs to be called if you don't want the engine to make up a permission
     * name for your dynamic permission.
     * 
     * @param dyanmicPermissionName
     * @param permission
     */
    public void registerDynamicPermission(String dynamicPermissionName,
            Permission permission) {
        this.getDynamicPermissionMap().put(dynamicPermissionName,
                permission.getName());
    }

    /**
     * Register a dynamic permission for passed UserName
     * @param processInstance
     * @param name
     * @throws RunTaskException
     */
    public void registerDynamicPermission(String dynamicPermissionName,
            String userName) throws RunTaskException {
        try {
            PermissionManager permissionManager = AvalonServiceHelper
                    .instance().getSecurityService().getPermissionManager();
            Permission permission = permissionManager
                    .getPermissionByName(userName);

            this.registerDynamicPermission(dynamicPermissionName, permission);
        } catch (InitializationException e) {
            log.error("Failed to get permission manager???", e);
            throw new RunTaskException(e);
        } catch (DataBackendException e) {
            log.error("Could not get permission:" + userName, e);
            throw new RunTaskException(e);
        } catch (UnknownEntityException e) {
            log.error("Could not get permission:" + userName, e);
            throw new RunTaskException(e);
        }
    }

    /**
     * Get the suffix for permissions for this process
     * 
     * @return
     */
    private String getSuffix() {
        if (this.getRelatedKey() != null && this.getRelatedClass() != null) {
            return this.getRelatedClass().getName()
                    + this.getRelatedKey().toString();
        } else {
            return this.getClass().getName() + this.getProcessInstanceId();
        }
    }

    /**
     * @hibernate.property @return Returns the processDefinitionId.
     */
    public Long getProcessDefinitionId() {
        return processDefinitionId;
    }

    /**
     * @param processDefinitionId
     *            The processDefinitionId to set.
     */
    public void setProcessDefinitionId(Long processDefinitionId) {
        this.processDefinitionId = processDefinitionId;
    }

    /**
     * @hibernate.set cascade="all-delete-orphan" lazy="true" inverse="true"
     * @hibernate.collection-key column="processInstanceId"
     * @hibernate.collection-one-to-many class="com.anite.antelope.zebra.om.AntelopeFOE"
     * @hibernate.collection-cache usage="transactional"
     * @return Returns the fOEs.
     */
    public Set getFOEs() {
        return fOES;
    }

    /**
     * @param es
     *            The fOEs to set.
     */
    public void setFOEs(Set es) {
        fOES = es;
    }

    /**
     * @hibernate.property @return Returns the relatedClass.
     */
    public Class getRelatedClass() {
        return relatedClass;
    }

    /**
     * @param relatedClass
     *            The relatedClass to set.
     */
    public void setRelatedClass(Class relatedClass) {
        this.relatedClass = relatedClass;
    }

    /**
     * @hibernate.property 
     * @return Returns the relatedKey.
     */
    public Long getRelatedKey() {
        return relatedKey;
    }

    /**
     * @param relatedKey
     *            The relatedKey to set.
     */
    public void setRelatedKey(Long relatedKey) {
        this.relatedKey = relatedKey;
    }

    /**
     * @hibernate.map cascade="all" lazy="true"
     * @hibernate.collection-index column="dynamicPermissionName" type="string"
     * @hibernate.collection-key column="processInstanceId"
     * @hibernate.collection-element column="realPermissionName" type="string"
     * @hibernate.collection-cache usage="transactional"
     * @return Returns the dynamicPermissionMap.
     */
    private Map getDynamicPermissionMap() {
        return dynamicPermissionMap;
    }

    /**
     * @param dynamicPermissionMap The dynamicPermissionMap to set.
     */
    private void setDynamicPermissionMap(Map dynamicPermissionMap) {
        this.dynamicPermissionMap = dynamicPermissionMap;
    }

    /**
     * Call this to declare presets for a task definition e.g. caption, due date, priority, owner
     * This will overwrite any existing preset for this task
     * 
     * Do not directly access this variable in the property set
     * 
     * @param presets
     * @param taskDefinition
     */
    public void registerTaskDefinitionPresets(
            AntelopeTaskInstancePresets presets, ITaskDefinition taskDefinition) {
        AntelopePropertySetEntry entry = new AntelopePropertySetEntry();

        entry.setObject(presets);
        this.getPropertySet().put(TASKPRESET + taskDefinition.getId(), entry);
    }

    /**
     * Call this to get presets for a task definition e.g. caption, due date, priority, owner
     * 
     * Do not directly access this variable in the property set
     * 
     * @param presets
     * @param taskDefinition
     */
    public AntelopeTaskInstancePresets getTaskDefinitionPresets(
            ITaskDefinition taskDefinition) {
        AntelopePropertySetEntry entry = (AntelopePropertySetEntry) this
                .getPropertySet().get(TASKPRESET + taskDefinition.getId());

        if (entry != null) {
            return (AntelopeTaskInstancePresets) entry.getObject();
        } else {
            return null;
        }
    }

    /**
     * Kill this process and all tasks within it.
     * This does NOT kill the parent process but will kill child processes
     * 
     * The application is expected to handle security over who can kill a process it is NOT enforced here
     * 
     * If this is a child process the subflow step will be marked complete
     * 
     * TODO talk to Matt about moving this into the core API of the engine
     * TODO write a unit test for this 
     * @throws NestableException
     * @throws HibernateException
     * @throws PersistenceException
     * @throws ComponentException
     * 
     */
    public void killProcess() throws PersistenceException, HibernateException,
            NestableException, ComponentException {
        IStateFactory stateFactory = ZebraHelper.getInstance()
                .getStateFactory();

        List processesToKill = this.getRunningChildProcesses();
        processesToKill.add(this);

        ITransaction t = stateFactory.beginTransaction();

        for (Iterator iter = processesToKill.iterator(); iter.hasNext();) {
            AntelopeProcessInstance process = (AntelopeProcessInstance) iter
                    .next();

            Set tasks = process.getTaskInstances();
            for (Iterator iterator = tasks.iterator(); iterator.hasNext();) {
                AntelopeTaskInstance task = (AntelopeTaskInstance) iterator
                        .next();

                task.setState(AntelopeTaskInstance.KILLED);
                task.setTaskOwner(UserLocator.getLoggedInUser());
                stateFactory.saveObject(task);

                // This will create history automatically and will remove itself from the set
                stateFactory.deleteObject(task);
                process.setState(AntelopeTaskInstance.KILLED);
                stateFactory.saveObject(process);
            }

        }
        t.commit();

        //Only destroy this process if there is a parent to force a subflow return
        //- no need to do the child tree - as they are all killed
        if (this.getParentProcessInstance() != null) {
            ProcessDestruct destructor = new ProcessDestruct();
            destructor.processDestruct(this);
        }
    }
}