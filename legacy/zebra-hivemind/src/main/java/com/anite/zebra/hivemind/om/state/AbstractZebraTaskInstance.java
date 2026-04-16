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

import java.util.Date;
import java.util.Iterator;
import java.util.Map;

import javax.persistence.Basic;
import javax.persistence.CascadeType;
import javax.persistence.Column;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.ManyToOne;
import javax.persistence.MappedSuperclass;
import javax.persistence.Transient;

import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.hibernate.dynamic.model.HibernateDynamicUser;
import org.apache.fulcrum.security.util.PermissionSet;

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;

/**
 * Abstract class for both Historical and Current task instances. It is done
 * this way to keep them in seperate tables as that is useful.
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
@MappedSuperclass
public abstract class AbstractZebraTaskInstance implements ITaskInstance {

    /* Properties for implementing the interface */
    private IFOE FOE;

    private ZebraProcessInstance processInstance;

    private long state;

    private Long taskInstanceId;

    /* Custom Properties */

    private String routingAnswer;

    private HibernateDynamicUser taskOwner;

    private String caption;

    private String description;

    private String outcome;

    private Date dateDue;

    private Date dateCreated;

    private Date actualCompletionDate;

    private HibernateDynamicUser decisionMadeBy;

    private Priority priority;

    private Long taskDefinitionId;

    /**
     * Boolean used to decide if this should be shown on any task list (set by
     * factory)
     */
    private boolean showInTaskList;

    /*
     * (non-Javadoc)
     * 
     * @see com.anite.antelope.zebra.modules.actionlet.Actionlet#doPerformTrigger(org.apache.turbine.util.RunData,
     *      org.apache.velocity.context.Context,
     *      com.anite.antelope.zebra.om.AntelopeTaskInstance,
     *      com.anite.antelope.zebra.om.AntelopeProcessInstance,
     *      com.anite.penguin.modules.tools.FormTool)
     */
    public static final String NOT_COMPLETED = "Not Completed";

    public static final String COMPLETED = "Completed";

    public Long getTaskDefinitionId() {
        return taskDefinitionId;
    }

    public void setTaskDefinitionId(Long taskDefinitionId) {
        this.taskDefinitionId = taskDefinitionId;
    }

    public AbstractZebraTaskInstance() {
        //noop
    }

    /**
     * Copy constructor Sets all fields EXCEPT for the instanceId
     * 
     * @param AntelopeTaskInstance
     *            a task instance
     */
    public AbstractZebraTaskInstance(AbstractZebraTaskInstance taskInstance) {
        /* Standard Properties */
        setFOE(taskInstance.getFOE());
        setState(taskInstance.getState());
        setProcessInstance((ZebraProcessInstance) taskInstance.getProcessInstance());
        setTaskDefinitionId(taskInstance.getTaskDefinitionId());

        setRoutingAnswer(taskInstance.getRoutingAnswer());
        setTaskOwner(taskInstance.getTaskOwner());
        setCaption(taskInstance.getCaption());
        setDateDue(taskInstance.getDateDue());
        setDateCreated(taskInstance.getDateCreated());
        setActualCompletionDate(taskInstance.getActualCompletionDate());
        setDecisionMadeBy(taskInstance.getDecisionMadeBy());
        setPriority(taskInstance.getPriority());
        setShowInTaskList(taskInstance.isShowInTaskList());
        setOutcome(taskInstance.getOutcome());
    }

    /* ITaskInstance methods */

    /**
     * @return Returns the taskInstanceId.
     */
    @Id
    @GeneratedValue
    public Long getTaskInstanceId() {
        return this.taskInstanceId;
    }

    /**
     * @param taskInstanceId
     *            The taskInstanceId to set.
     */
    public void setTaskInstanceId(Long taskInstanceId) {
        this.taskInstanceId = taskInstanceId;
    }

    /**
     * @return
     */
    @ManyToOne(targetEntity = ZebraProcessInstance.class, cascade = { CascadeType.MERGE, CascadeType.PERSIST })
    public IProcessInstance getProcessInstance() {
        return this.processInstance;
    }

    /**
     * Provides a pre-casted version of the process instance
     * 
     * @return
     */
    @Transient
    public ZebraProcessInstance getZebraProcessInstance() {
        return this.processInstance;
    }

    public void setProcessInstance(ZebraProcessInstance processInstance) {
        this.processInstance = processInstance;
    }

    @Basic
    public long getState() {
        return this.state;
    }

    public void setState(long newState) {
        this.state = newState;
    }

    @Transient
    public ITaskDefinition getTaskDefinition() throws DefinitionNotFoundException {
        ZebraDefinitionFactory definitons = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry()
                .getService("zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);
        return definitons.getTaskDefinition(this.taskDefinitionId);
    }

    /**
     * @param taskDefinition
     *            The taskDefinition to set.
     */
    public void setTaskDefinition(ZebraTaskDefinition taskDefinition) {

        this.taskDefinitionId = taskDefinition.getId();
    }

    @ManyToOne(targetEntity = ZebraFOE.class, cascade = { CascadeType.PERSIST, CascadeType.MERGE })
    public IFOE getFOE() {
        return this.FOE;
    }

    public void setFOE(IFOE foe) {
        this.FOE = foe;
    }

    /* Custom Methods */

    @Basic
    public String getRoutingAnswer() {
        return this.routingAnswer;
    }

    public void setRoutingAnswer(String routingAnswer) {
        this.routingAnswer = routingAnswer;
    }

    @ManyToOne
    public HibernateDynamicUser getTaskOwner() {
        return this.taskOwner;
    }

    public void setTaskOwner(HibernateDynamicUser user) {
        this.taskOwner = user;
    }

    @Basic
    public String getCaption() {
        try {
            if (this.caption == null && this.getTaskDefinition() != null) {
                this.caption = ((ZebraTaskDefinition) this.getTaskDefinition()).getName();
            }
            return this.caption;
        } catch (DefinitionNotFoundException e) {
           throw new NestableRuntimeException(e);
        }
    }

    /**
     * @param caption
     *            The caption to set.
     */
    public void setCaption(String caption) {
        this.caption = caption;
    }

    /**
     * @return Returns the dateCreated.
     * 
     */
    @Basic
    public Date getDateCreated() {
        return this.dateCreated;
    }

    /**
     * @param dateCreated
     *            The dateCreated to set.
     */
    public void setDateCreated(Date dateCreated) {
        this.dateCreated = dateCreated;
    }

    /**
     * @return Returns the dateDue.
     * @hibernate.property
     */
    @Basic
    public Date getDateDue() {
        return this.dateDue;
    }

    /**
     * @param dateDue
     *            The dateDue to set.
     */
    public void setDateDue(Date dateDue) {
        this.dateDue = dateDue;
    }

    /**
     * @return Returns the actualCompletionDate.
     */
    @Basic
    public Date getActualCompletionDate() {
        return this.actualCompletionDate;
    }

    /**
     * sets the "actual" completion date for the task; this is in addition to
     * the completion date that is automatically set
     * 
     * @param date
     *            date of actual completion
     * 
     */
    public void setActualCompletionDate(Date actualCompletionDate) {
        this.actualCompletionDate = actualCompletionDate;
    }

    /**
     * @return
     */
    @ManyToOne
    public HibernateDynamicUser getDecisionMadeBy() {
        return this.decisionMadeBy;
    }

    /**
     * sets the "actual" person who made the decision for the task; this is in
     * addition to the task owner who completed the task that is automatically
     * set
     */
    public void setDecisionMadeBy(HibernateDynamicUser decisionMadeBy) {
        this.decisionMadeBy = decisionMadeBy;
    }

    /**
     * Returns required permissions for this task (both dynamic and static)
     * 
     * @return
     * @throws net.sf.hibernate.exception.NestableException
     * @throws NestableException
     */
    @Transient
    public PermissionSet getPermissions() {
        try {
            // Static
            PermissionSet permissions = new PermissionSet();
            ZebraTaskDefinition antelopeTaskDefinition = (ZebraTaskDefinition) this.getTaskDefinition();
            PermissionSet staticPermissions = antelopeTaskDefinition.getStaticPermissions();
            permissions.add(staticPermissions);

            // Dynamic
            ZebraProcessInstance antelopeProcessInstance = (ZebraProcessInstance) this.getProcessInstance();
            PermissionSet dynamicPermissionSet = antelopeProcessInstance.getDynamicPermissions(antelopeTaskDefinition
                    .getDynamicPermissions());
            permissions.add(dynamicPermissionSet);

            return permissions;
        } catch (DefinitionNotFoundException e) {
            throw new NestableRuntimeException(e);
        }
    }

    @Transient
    public String getCommaSeperatedPermissions() throws NestableException {
        PermissionSet permissions = this.getPermissions();
        StringBuffer permissionList = new StringBuffer();

        boolean first = true;
        for (Iterator iter = permissions.iterator(); iter.hasNext();) {
            if (first) {
                first = false;
            } else {
                permissionList.append(", ");
            }

            Permission permission = (Permission) iter.next();
            permissionList.append(permission.getName());
        }

        return permissionList.toString();
    }

    /**
     * Gets the property set for the process that does with this This is a
     * shortcut for those who don't want to call this directly on the process
     * instance
     */
    @Transient
    public Map getProcessPropertySet() {
        return this.getZebraProcessInstance().getPropertySet();
    }

    /**
     * @hibernate.property
     * @return Returns the showInTaskList.
     */
    @Basic
    public boolean isShowInTaskList() {
        return this.showInTaskList;
    }

    /**
     * @param showInTaskList
     *            The showInTaskList to set.
     */
    public void setShowInTaskList(boolean showInTaskList) {
        this.showInTaskList = showInTaskList;
    }

    /**
     * @return Returns the priority.
     */
    @ManyToOne
    public Priority getPriority() {
        return this.priority;
    }

    /**
     * @param priority
     *            The priority to set.
     */
    public void setPriority(Priority priority) {
        this.priority = priority;
    }

    /**
     * This is the detailed description of this step - this is not used by the
     * engine but may be useful for example for showing in the history
     * 
     * @return Returns the description.
     */
    @Basic
    @Column(length = 4000)
    public String getDescription() {
        return this.description;
    }

    /**
     * @param description
     *            The description to set.
     */
    public void setDescription(String description) {
        this.description = description;
    }

    /**
     * @return Returns the outcome.
     */
    @Basic
    public String getOutcome() {
        return this.outcome;
    }

    /**
     * @param outcome
     *            The outcome to set.
     */
    public void setOutcome(String outcome) {
        this.outcome = outcome;
    }
}