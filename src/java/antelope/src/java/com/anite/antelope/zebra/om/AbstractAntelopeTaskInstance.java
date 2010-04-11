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
import java.util.Iterator;
import java.util.Map;

import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.PermissionSet;

import com.anite.antelope.utils.CalendarHelper;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Abstract class for both Historical and Current task instances. It is done this way
 * to keep them in seperate tables as that is useful.
 * @author Matthew.Norris
 * @author Ben Gidley
 * @hibernate.cache usage="transactional"
 */
public abstract class AbstractAntelopeTaskInstance implements ITaskInstance {

    private final static Log log = LogFactory
            .getLog(AbstractAntelopeTaskInstance.class);

    /* Properties for implementing the interface */
    private IFOE FOE;

    private AntelopeProcessInstance processInstance;

    private long state;

    private AntelopeTaskDefinition taskDefinition;

    private Long taskInstanceId;

    /* Custom Properties */

    private String routingAnswer;

    private User taskOwner;

    private String caption;

    private String description;
    
    private String outcome;

    private Date dateDue;

    private Date dateCreated;

    private Date actualCompletionDate;

    private User decisionMadeBy;

    private Priority priority;
    
    /**
     * Boolean used to decide if this should be shown on any
     * task list (set by factory)
     */
    private boolean showInTaskList;

    /* (non-Javadoc)
     * @see com.anite.antelope.zebra.modules.actionlet.Actionlet#doPerformTrigger(org.apache.turbine.util.RunData, org.apache.velocity.context.Context, com.anite.antelope.zebra.om.AntelopeTaskInstance, com.anite.antelope.zebra.om.AntelopeProcessInstance, com.anite.penguin.modules.tools.FormTool)
     */
    public static final String NOT_COMPLETED = "Not Completed";

    public static final String COMPLETED = "Completed";

    public AbstractAntelopeTaskInstance() {
    }

    /**
     * Copy constructor
     * Sets all fields EXCEPT for the instanceId
     * @param AntelopeTaskInstance a task instance
     */
    public AbstractAntelopeTaskInstance(
            AbstractAntelopeTaskInstance taskInstance)
            throws DefinitionNotFoundException {
        /* Standard Properties */
        setFOE(taskInstance.getFOE());
        setState(taskInstance.getState());
        setProcessInstance((AntelopeProcessInstance) taskInstance
                .getProcessInstance());
        setTaskDefinition((AntelopeTaskDefinition) taskInstance
                .getTaskDefinition());

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
     * @hibernate.id generator-class="native"
     */
    public Long getTaskInstanceId() {
        return taskInstanceId;
    }

    /**
     * @param taskInstanceId
     *            The taskInstanceId to set.
     */
    public void setTaskInstanceId(Long taskInstanceId) {
        this.taskInstanceId = taskInstanceId;
    }

    /**
     * @hibernate.many-to-one column="processInstanceId" not-null="true"
     *                        class="com.anite.antelope.zebra.om.AntelopeProcessInstance"
     *                        cascade="all"
     * @hibernate.column name="processInstanceId"
     * @return
     */
    public IProcessInstance getProcessInstance() {
        return this.processInstance;
    }

    /**
     * Provides a pre-casted version of the process instance
     * @return
     */
    public AntelopeProcessInstance getAntelopeProcessInstance() {
        return this.processInstance;
    }

    public void setProcessInstance(AntelopeProcessInstance processInstance) {
        this.processInstance = processInstance;
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
     *  @hibernate.many-to-one column="taskDefinition" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopeTaskDefinition"
     *                        cascade="none"
     */
    public ITaskDefinition getTaskDefinition() {
        return this.taskDefinition;
    }

    /**
     * @param taskDefinition The taskDefinition to set.
     */
    public void setTaskDefinition(AntelopeTaskDefinition taskDefinition) {
        this.taskDefinition = taskDefinition;
    }

    /**
     * @hibernate.many-to-one column="taskFoe" not-null="false"
     *                        class="com.anite.antelope.zebra.om.AntelopeFOE"
     *                        cascade="save-update"
     */
    public IFOE getFOE() {
        return FOE;
    }

    public void setFOE(IFOE foe) {
        FOE = foe;
    }

    /* Custom Methods */

    /**
     * @hibernate.property 
     * 
     */
    public String getRoutingAnswer() {
        return this.routingAnswer;
    }

    public void setRoutingAnswer(String routingAnswer) {
        this.routingAnswer = routingAnswer;
    }

    /**
     * @hibernate.many-to-one column="taskOwnerId" not-null="false"
     *                        class="org.apache.fulcrum.security.model.dynamic.entity.DynamicUser"
     *                        cascade="save-update"
     * @return
     */
    public User getTaskOwner() {
        return this.taskOwner;
    }

    /**
     * Velocity Friendly task owner accessor
     * @return
     */
    public String getStringTaskOwner() {
        if (this.getTaskOwner() == null) {
            return "";
        } else {
            return this.getTaskOwner().getName();
        }
    }

    public void setTaskOwner(User user) {
        this.taskOwner = user;
    }

    /**
     * @hibernate.property 
     * @return Returns the caption.
     */

    public String getCaption() {
        if (caption == null && this.getTaskDefinition() != null) {
            caption = ((AntelopeTaskDefinition) this.getTaskDefinition())
                    .getName();
        }
        return this.caption;
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
     * @hibernate.property
     */
    public Date getDateCreated() {
        return dateCreated;
    }

    /**
     * Velocity friendly accessor for Date Created
     * @return
     */
    public String getStringDateCreated() {
        if (this.getDateCreated() == null) {
            return "";
        }
        return CalendarHelper.getInstance().getFormattedDate(
                this.getDateCreated());

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
    public Date getDateDue() {
        return dateDue;
    }

    /**
     * Velocity friendly accessor for DateDue
     */
    public String getStringDateDue() {
        if (this.getDateDue() == null) {
            return "";
        } else {
            return CalendarHelper.getInstance().getFormattedDate(
                    this.getDateDue());

        }
    }

    /**
     * @param dateDue
     *            The dateDue to set.
     */
    public void setDateDue(Date dateDue) {
        this.dateDue = dateDue;
    }

    /**
     * @hibernate.property not-null="false"
     * @return Returns the actualCompletionDate.
     */
    public Date getActualCompletionDate() {
        return actualCompletionDate;
    }

    
    /**
     * Velocity Friendly getActualCompletionDate
     * @return
     */
    public String getStringActualCompletionDate() {
        if (this.getActualCompletionDate() == null) {
            return "";
        } else {
            return CalendarHelper.getInstance().getFormattedDate(this.getActualCompletionDate());
        }
    }

    /**
     * sets the "actual" completion date for the task; this is in addition to
     * the completion date that is automatically set
     * 
     * @param date
     *            date of actual completion
     * @throws BaseCtmsException
     *             base ctms exception
     */
    public void setActualCompletionDate(Date actualCompletionDate) {
        this.actualCompletionDate = actualCompletionDate;
    }

    /**
     * @hibernate.many-to-one column="decisionMadeBy" not-null="false"
     *                        class="org.apache.fulcrum.security.model.dynamic.entity.DynamicUser"
     *                        cascade="save-update"
     * @return
     */
    public User getDecisionMadeBy() {
        return this.decisionMadeBy;
    }

    /**
     * sets the "actual" person who made the decision for the task; this is in
     * addition to the task owner who completed the task that is automatically
     * set
     */
    public void setDecisionMadeBy(User decisionMadeBy) {
        this.decisionMadeBy = decisionMadeBy;
    }

    /**
     * Returns required permissions for this task
     * (both dynamic and static)
     * @return
     * @throws net.sf.hibernate.exception.NestableException
     * @throws NestableException
     */
    public PermissionSet getPermissions() throws NestableException {
        // Static
        PermissionSet permissions = new PermissionSet();
        AntelopeTaskDefinition antelopeTaskDefinition = (AntelopeTaskDefinition) this
                .getTaskDefinition();
        PermissionSet staticPermissions = antelopeTaskDefinition
                .getStaticPermissions();
        permissions.add(staticPermissions);

        // Dynamic
        AntelopeProcessInstance antelopeProcessInstance = (AntelopeProcessInstance) this
                .getProcessInstance();
        PermissionSet dynamicPermissionSet = antelopeProcessInstance
                .getDynamicPermissions(antelopeTaskDefinition
                        .getDynamicPermissions());
        permissions.add(dynamicPermissionSet);

        return permissions;
    }

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
     * Gets the property set for the process that does with this
     * This is a shortcut for those who don't want to call this
     * directly on the process instance 
     */
    public Map getProcessPropertySet() {
        return this.getAntelopeProcessInstance().getPropertySet();
    }

    /**
     * @hibernate.property
     * @return Returns the showInTaskList.
     */
    public boolean isShowInTaskList() {
        return showInTaskList;
    }

    /**
     * @param showInTaskList The showInTaskList to set.
     */
    public void setShowInTaskList(boolean showInTaskList) {
        this.showInTaskList = showInTaskList;
    }

    /**
     * @hibernate.many-to-one cascade="none"
     * @return Returns the priority.
     */
    public Priority getPriority() {
        return priority;
    }

    /**
     * @param priority The priority to set.
     */
    public void setPriority(Priority priority) {
        this.priority = priority;
    }

    /**
     * This is the detailed description of this step - this is not used by the engine but may be useful
     * for example for showing in the history
     * @hibernate.property length="4000"
     * @return Returns the description.
     */
    public String getDescription() {
        return description;
    }

    /**
     * @param description The description to set.
     */
    public void setDescription(String description) {
        this.description = description;
    }

    /**
     * @hibernate.proprerty
     * @return Returns the outcome.
     */
    public String getOutcome() {
        return outcome;
    }
    
    /**
     * @param outcome The outcome to set.
     */
    public void setOutcome(String outcome) {
        this.outcome = outcome;
    }
}