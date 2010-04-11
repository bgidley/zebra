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

package com.anite.zebra.hivemind.om.state;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.Stack;

import javax.persistence.Basic;
import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.ManyToOne;
import javax.persistence.MapKey;
import javax.persistence.OneToMany;
import javax.persistence.PersistenceException;
import javax.persistence.Transient;

import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.hibernate.dynamic.model.HibernateDynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.hibernate.HibernateException;
import org.hibernate.Query;
import org.hibernate.Session;
import org.hibernate.annotations.Cascade;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.impl.ZebraSecurity;
import com.anite.zebra.hivemind.util.RegistryHelper;

/**
 * A Zebra Process Instance reflect an instance of a Process Definition. This
 * class implements the core interface and add additional properties as commonly
 * required by the applications This class can be extended, but this should not
 * be necessary.
 * 
 * This implementation supports subflows and dynamic workflow security.
 * 
 * See ZebraSecuity for more details
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
@Entity
public class ZebraProcessInstance implements IProcessInstance {

    private static final String ZEBRA_PERMISSION_PREFIX = "ZEBRA";

    private static Log log = LogFactory.getLog(ZebraProcessInstance.class);

    /* Field Variables for Interface */
    private Long processDefinitionId;

    private Long processInstanceId = null;

    private long state;

    private Set<ZebraTaskInstance> taskInstances = new HashSet<ZebraTaskInstance>();

    /* Custom behavioural properties */
    /** Parent Process used for subflows */
    private ZebraProcessInstance parentProcessInstance;

    /** Task instance from parent for subflow step */
    private ITaskInstance parentTaskInstance;

    /* Custom Informational Properties */
    /** The user friendly name of this process */
    private String processName;

    /** The user that activated this process */
    private HibernateDynamicUser activatedBy;

    /** The property set catch all for anything at all */
    private Map<String, ZebraPropertySetEntry> propertySet = new HashMap<String, ZebraPropertySetEntry>();

    /** Set of historical task instance information */
    private Set<ZebraTaskInstanceHistory> historyInstances = new HashSet<ZebraTaskInstanceHistory>();

    /**
     * Maps dynamic permission names to fulcrum security permission names
     */
    private Map<String, String> dynamicPermissionMap = new HashMap<String, String>();

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
    private Set<ZebraFOE> fOES = new HashSet<ZebraFOE>();

    /**
     * Default constructor for normal construction
     */
    public ZebraProcessInstance() {
        // noop
    }

    /**
     * constructor from another instance (e.g. for history)
     * 
     * @param processInstance
     *            AntelopeProcessInstance
     */
    public ZebraProcessInstance(ZebraProcessInstance processInstance) throws NestableException {
        if (processInstance == null) {
            throw new NestableException(
                    "Cannot instantiate ProcessInstance class without a valid ProcessInstance object");
        }
    }

    /**
     * @return Returns the processDefinitionId.
     */
    @Basic
    public Long getProcessDefinitionId() {
        return this.processDefinitionId;
    }

    /**
     * @param processDefinitionId
     *            The processDefinitionId to set.
     */
    public void setProcessDefinitionId(Long processDefinitionId) {
        this.processDefinitionId = processDefinitionId;
    }

    /**
     * @return Returns the fOEs.
     */
    @OneToMany()
    @Cascade({org.hibernate.annotations.CascadeType.ALL, org.hibernate.annotations.CascadeType.DELETE_ORPHAN})
    public Set<ZebraFOE> getFOEs() {
        return this.fOES;
    }

    /**
     * @param es
     *            The fOEs to set.
     */
    public void setFOEs(Set<ZebraFOE> es) {
        this.fOES = es;
    }

    /**
     * @return Returns the relatedClass.
     */
    @Basic
    public Class getRelatedClass() {
        return this.relatedClass;
    }

    /**
     * @param relatedClass
     *            The relatedClass to set.
     */
    public void setRelatedClass(Class relatedClass) {
        this.relatedClass = relatedClass;
    }

    /**
     * @return Returns the relatedKey.
     */
    @Basic
    public Long getRelatedKey() {
        return this.relatedKey;
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
     * 
     * @TODO implement me using CollectionOfElements once Hibernate Annonations B7 is integrated
     */
    @Transient
    //  @OneToMany(cascade=CascadeType.ALL, fetch=FetchType.LAZY)
    //  @MapKey
    //  @JoinTable(table=@Table(name="ProcessInstanceDynamicPermissions"), joinColumns= @JoinColumn(name="dynamicPermissionName"))
    //  @Column(name="realPermissionName")
    public Map<String, String> getDynamicPermissionMap() {
        return this.dynamicPermissionMap;
    }

    /**
     * @param dynamicPermissionMap
     *            The dynamicPermissionMap to set.
     */
    public void setDynamicPermissionMap(Map<String, String> dynamicPermissionMap) {
        this.dynamicPermissionMap = dynamicPermissionMap;
    }

    /* IProcessInstance Methods */

    /**
     * Interface method for get the Process definition Note this should never
     * actually throw definition not found exception as that would imply this
     * instance can't exist. Which it does!
     */
    @Transient
    public IProcessDefinition getProcessDef() throws DefinitionNotFoundException {

        ZebraDefinitionFactory definitons = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry()
                .getService("zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);
        return definitons.getProcessDefinitionById(this.processDefinitionId);

    }

    /**
     * This the unique ID of the process in the database
     * 
     * @return Returns the processInstanceId.
     * 
     */
    @Id @GeneratedValue
    public Long getProcessInstanceId() {
        return this.processInstanceId;
    }

    /**
     * @param processInstanceId
     *            The processInstanceId to set.
     */
    public void setProcessInstanceId(Long processInstanceId) {
        this.processInstanceId = processInstanceId;
    }

    /**
     * This is the state constant defined in Zebra
     */
    @Basic
    public long getState() {
        return this.state;
    }

    public void setState(long newState) {
        this.state = newState;
    }

    /**
     * @return
     */
    @OneToMany(cascade = CascadeType.ALL)
    @JoinColumn(name = "processInstanceId")
    public Set<ZebraTaskInstance> getTaskInstances() {
        return this.taskInstances;
    }

    public void setTaskInstances(Set<ZebraTaskInstance> taskInstances) {
        this.taskInstances = taskInstances;
    }

    /* Implementation Methods */

    /**
     * @return Returns the parentProcessInstance.
     */
    @ManyToOne
    public ZebraProcessInstance getParentProcessInstance() {
        return this.parentProcessInstance;
    }

    /**
     * @param parentProcessInstance
     *            The parentProcessInstance to set.
     */
    public void setParentProcessInstance(ZebraProcessInstance parentProcessInstance) {
        this.parentProcessInstance = parentProcessInstance;
    }

    /**
     * The process property set.
     * 
     * This is a set of ZebraProperty Set Entry objects. These in turn can hold
     * almost anythings
     * 
     * You can easily introduce performance issues by putting too much in here!
     * Real data should reside in a related table. This should ONLY hold items
     * needed to process the flow.
     * 
     * Items in here are effectively disposed of when the flow ends.
     * 
     * Items are only passed back and forth from subflows if explictly marked to
     * do so in the designer. For those used to earlier versions of zebra push
     * outputs has been removed.
     * 
     * @return
     */
    @OneToMany(cascade = CascadeType.ALL, fetch=FetchType.LAZY, mappedBy="processInstance")
    @MapKey(name="key")
    public Map<String, ZebraPropertySetEntry> getPropertySet() {
        return this.propertySet;
    }

    public void setPropertySet(Map<String, ZebraPropertySetEntry> propertySetEntries) {
        this.propertySet = propertySetEntries;
    }
    
    /**
     * A helper function to ensure the referential integrity in maintained
     * @param key
     * @param entry
     */
    public void addPropertySetEntry(String key, ZebraPropertySetEntry entry){
        entry.setKey(key);
        entry.setProcessInstance(this);
        this.getPropertySet().put(key, entry);
    }

    /**
     * Remove item from the property set
     * @param key
     */
    public void removePropertySetEntry(String key){
        ZebraPropertySetEntry entry = this.getPropertySet().get(key);
        if (entry != null){
            entry.setKey(null);
            entry.setProcessInstance(null);
        }
        this.getPropertySet().remove(key);        
    }
    
    /**
     * @return Returns the processName.
     */
    @Basic
    public String getProcessName() {
        return this.processName;
    }

    /**
     * @param processName
     *            The processName to set.
     */
    public void setProcessName(String processName) {
        this.processName = processName;
    }

    /**
     * The user that actived this step.
     * 
     * This is usually the owner except in a case of delegation. IN that case it
     * is the delegatee
     * 
     * @return
     */
    @ManyToOne
    public HibernateDynamicUser getActivatedBy() {
        return this.activatedBy;
    }

    public void setActivatedBy(HibernateDynamicUser activatedBy) {
        this.activatedBy = activatedBy;
    }

    /**
     * @return
     */
    @OneToMany(fetch = FetchType.LAZY, cascade={CascadeType.ALL})
    public Set<ZebraTaskInstanceHistory> getHistoryInstances() {
        return this.historyInstances;
    }

    public void setHistoryInstances(Set<ZebraTaskInstanceHistory> historyInstances) {
        this.historyInstances = historyInstances;
    }

    @ManyToOne(targetEntity = ZebraTaskInstance.class)
    public ITaskInstance getParentTaskInstance() {
        return this.parentTaskInstance;
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
    @Transient
    public List<ZebraProcessInstance> getRunningChildProcesses() {

        List<ZebraProcessInstance> results = new ArrayList<ZebraProcessInstance>();

        String querySQL = "select api from ZebraProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";
        querySQL += " and api.state=:state";

        Session s = RegistryHelper.getInstance().getSession();
        Query q = s.createQuery(querySQL);
        q.setCacheable(true);
        q.setLong("state", IProcessInstance.STATE_RUNNING);

        // Recursive Process children
        recursivelyQueryChildProcesses(results, q);
        return results;
    }

    @SuppressWarnings("unchecked")
	@Transient
    public List<ZebraProcessInstance> getRunningRelatedProcesses() {
        List<ZebraProcessInstance> results = new ArrayList<ZebraProcessInstance>();

        if (this.getRelatedKey() != null) {

            String querySQL = "select api from ZebraProcessInstance api where api.relatedClass =:relatedClass";
            querySQL += " and api.relatedKey = :relatedKey";
            querySQL += " and api.state=:state";

            Session s = RegistryHelper.getInstance().getSession();
            Query q = s.createQuery(querySQL);
            q.setCacheable(true);
            q.setParameter("relatedClass", this.getRelatedClass());
            q.setLong("relatedKey", this.getRelatedKey().longValue());
            q.setLong("state", IProcessInstance.STATE_RUNNING);
            results = q.list();
        }
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
    @SuppressWarnings("unchecked")
	@Transient
    public List<ZebraProcessInstance> getCompleteRelatedProcesses() {
    	List<ZebraProcessInstance> results = new ArrayList<ZebraProcessInstance>();
        if (this.getRelatedKey() != null) {

            String querySQL = "select api from ZebraProcessInstance api where api.relatedClass =:relatedClass";
            querySQL += " and api.relatedKey = :relatedKey";
            querySQL += " and api.state=:state";

            Session s = RegistryHelper.getInstance().getSession();
            Query q = s.createQuery(querySQL);
            q.setCacheable(true);
            q.setParameter("relatedClass", this.getRelatedClass());
            q.setParameter("relatedKey", this.getRelatedKey());
            q.setLong("state", IProcessInstance.STATE_COMPLETE);

            results = q.list();
        }
        return results;
    }

    /**
     * Get all child processes not running (e.g. complete and killed)
     * 
     * @return
     * @throws PersistenceException
     * @throws HibernateException
     */
    @Transient
    public List<ZebraProcessInstance> getNotRunningChildProcesses() throws HibernateException {
        List<ZebraProcessInstance> results = new ArrayList<ZebraProcessInstance>();

        String querySQL = "select api from ZebraProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";
        querySQL += " and api.state!=:state";

        Session s = RegistryHelper.getInstance().getSession();
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
    @Transient
    private void recursivelyQueryChildProcesses(List<ZebraProcessInstance> results, Query q) throws HibernateException {
        // Recursive Process children
        Stack<ZebraProcessInstance> checkList = new Stack<ZebraProcessInstance>();
        checkList.push(this);
        while (!checkList.isEmpty()) {
            ZebraProcessInstance processInstance = checkList.pop();
            q.setLong("guid", processInstance.getProcessInstanceId().longValue());
            for (Iterator it = q.iterate(); it.hasNext();) {
                ZebraProcessInstance childProcess = (ZebraProcessInstance) it.next();
                results.add(childProcess);
                checkList.push(childProcess);
            }
        }
    }

    /**
     * Get all child processes regardless of state
     * 
     * @return
     * @throws PersistenceException
     * @throws HibernateException
     */
    @Transient
    public List<ZebraProcessInstance> getAllChildProcesses() {
        List<ZebraProcessInstance> results = new ArrayList<ZebraProcessInstance>();

        String querySQL = "select api from ZebraProcessInstance api where api.parentProcessInstance.processInstanceId =:guid";

        Session s = RegistryHelper.getInstance().getSession();
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
    @SuppressWarnings("unchecked")
    @Transient
    public List<ZebraTaskInstance> getUsersTasks() {

        Session session = RegistryHelper.getInstance().getSession();
        ;
        Query tasks = session.getNamedQuery("tasks");
        tasks.setParameter("processInstance", this);
        tasks.setParameter("showInTaskList", Boolean.TRUE);

        return tasks.list();
    }

    /**
     * Looks for the first list of tasks that come from the child(ren) of this
     * processinstance This is used for finding the next screen. We don't do
     * this exaustively as it could be very large. The first is good enough for
     * determining the next screen
     */
    @Transient
    public List<ZebraTaskInstance> getFirstTasksFromAChildProcess() throws NestableException {

        Stack<ZebraProcessInstance> checkList = new Stack<ZebraProcessInstance>();
        checkList.push(this);
        while (!checkList.isEmpty()) {
            try {
                ZebraProcessInstance currentProcess = checkList.pop();
                List childProcesses = currentProcess.getRunningChildProcesses();
                for (Iterator it = childProcesses.iterator(); it.hasNext();) {
                    ZebraProcessInstance child = (ZebraProcessInstance) it.next();
                    List<ZebraTaskInstance> allTasks = child.getUsersTasks();
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
        return new ArrayList<ZebraTaskInstance>();
    }

    /**
     * looks for tasks from the parent(s) of the processInstance
     * 
     * @return
     */
    @Transient
    public List getFirstTasksFromAParentProcess() throws NestableException {
        ZebraProcessInstance parentInstance = null;
        try {
            parentInstance = this.getParentProcessInstance();
            while (parentInstance != null) {
                if (log.isInfoEnabled()) {
                    log.info("Getting tasks for parent process  " + this.getProcessInstanceId());
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
     * Gets the fulcrum permission object for a dynamic permission name
     * 
     * @param permissionNames
     * @return
     * @throws NestableException
     */
    @Transient
    public PermissionSet getDynamicPermissions(String permissionNames) {
        if (permissionNames != null) {

            String[] actualPermissionNames = permissionNames.split(";");

            for (int i = 0; i < actualPermissionNames.length; i++) {
                actualPermissionNames[i] = getDynamicPermission(actualPermissionNames[i]);
            }

            return getZebraSecurity().getPermissionSet(actualPermissionNames);
        }
        return new PermissionSet();
    }

    @Transient
    private ZebraSecurity getZebraSecurity() {
        return (ZebraSecurity) RegistryManager.getInstance().getRegistry().getService("zebra.ZebraSecurity",
                ZebraSecurity.class);

    }

    /**
     * Gets the actual permission for passed dynamic perission name
     * 
     * If you want to grant a user a dynamic permission call this function to
     * find out what permission to grant.
     * 
     * If on the other hand you want to link an existing permission to a dynamic
     * permission named call registerDynamicPermission
     * 
     * @param permissionName
     * @return
     * @throws NestableException
     */
    @Transient
    public String getDynamicPermission(String permissionName) {
        if (permissionName != null) {

            if (!this.getDynamicPermissionMap().containsKey(permissionName)) {
                // Otherwise bind permision to related class/ourselves
                String suffix = this.getSuffix();
                String actualPermissionName = ZEBRA_PERMISSION_PREFIX + permissionName + "[" + suffix + "]";

                // check permission exists if not create it
                Permission permission = getZebraSecurity().loadOrCreatePermission(actualPermissionName);

                // add to dynamic map
                this.registerDynamicPermission(permissionName, permission);

            }
            // first look in the map
            return this.getDynamicPermissionMap().get(permissionName);
        }
        return null;
    }

    /**
     * Call this to register a fulcrum permission to a an dynamic permission
     * name From this point onwards that dynamic permissionName will satify the
     * workflow engine
     * 
     * If called for a permission already registered it is replaced.
     * 
     * This only needs to be called if you don't want the engine to make up a
     * permission name for your dynamic permission.
     * 
     * @param dyanmicPermissionName
     * @param permission
     */
    @Transient
    public void registerDynamicPermission(String dynamicPermissionName, Permission permission) {
        this.getDynamicPermissionMap().put(dynamicPermissionName, permission.getName());
    }

    /**
     * Register a dynamic permission for passed UserName
     * 
     * @param processInstance
     * @param name
     * @throws RunTaskException
     */
    @Transient
    public void registerDynamicPermission(String dynamicPermissionName, String userName) throws RunTaskException {
        try {
            PermissionManager permissionManager = getZebraSecurity().getPermissionManager();
            Permission permission = permissionManager.getPermissionByName(userName);

            this.registerDynamicPermission(dynamicPermissionName, permission);

        } catch (EntityDisabledException e) {
            log.error("Could not get permission:" + userName, e);
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
    @Transient
    private String getSuffix() {
        if (this.getRelatedKey() != null && this.getRelatedClass() != null) {
            return this.getRelatedClass().getName() + this.getRelatedKey().toString();
        } else {
            return this.getClass().getName() + this.getProcessInstanceId();
        }
    }

    @Override
    public String toString() {
    	if (this.getProcessInstanceId() != null) {
    		return this.getProcessInstanceId().toString();
    	} else {
    		return super.toString();
    	}
    }
}