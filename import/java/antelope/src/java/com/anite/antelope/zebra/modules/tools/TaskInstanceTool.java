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

package com.anite.antelope.zebra.modules.tools;

import java.util.Date;
import java.util.Map;

import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.entity.User;
import org.apache.turbine.services.pull.ApplicationTool;
import org.apache.turbine.util.RunData;

import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * A request tool to provide current task instance information
 * @author Ben.Gidley
 */
public class TaskInstanceTool implements ApplicationTool {

    private static final Log log = LogFactory.getLog(TaskInstanceTool.class);

    private AntelopeTaskInstance taskInstance;
 

    private RunData runData;

    public static final String DEFAULT_TOOL_NAME = "task";

    public void init(Object data) {
        runData = (RunData) data;
        initialise();
    }

    /**
     * Initialise Tool Now (called if task changes by the base class)
     */
    public void initialise() {
        ZebraSessionData zebraSession = (ZebraSessionData) runData.getSession()
                .getAttribute(ZebraSessionData.SESSION_KEY);

        if (zebraSession != null) {
            try {
                this.taskInstance = zebraSession.getTaskInstance();
            } catch (NestableException e) {
                // Nothing to see here
                // Move on without zebra information
                log.error("Problem loading zebra session data", e);
            }
        }
    }

    /**
     * DO NOT USE THIS
     * It has no effect on request tools 
     */
    public void refresh() {
        // NOOP
    }

    /* (non-Javadoc)
     * @see java.lang.Object#equals(java.lang.Object)
     */
    public boolean equals(Object obj) {
        return taskInstance.equals(obj);
    }
    /**
     * @return
     */
    public Date getActualCompletionDate() {
        return taskInstance.getActualCompletionDate();
    }
    /**
     * @return
     */
    public String getCaption() {
        return taskInstance.getCaption();
    }
    /**
     * @return
     */
    public Date getDateCreated() {
        return taskInstance.getDateCreated();
    }
    /**
     * @return
     */
    public Date getDateDue() {
        return taskInstance.getDateDue();
    }
    /**
     * @return
     */
    public User getDecisionMadeBy() {
        return taskInstance.getDecisionMadeBy();
    }
    /**
     * @return
     */
    public IFOE getFOE() {
        return taskInstance.getFOE();
    }
    /**
     * @return
     */
    public IProcessInstance getProcessInstance() {
        return taskInstance.getProcessInstance();
    }
    /**
     * @return
     */
    public Map getPropertySetEntries() {
        return taskInstance.getPropertySet();
    }
    /**
     * @return
     */
    public String getRoutingAnswer() {
        return taskInstance.getRoutingAnswer();
    }
    /**
     * @return
     */
    public long getState() {
        return taskInstance.getState();
    }
    /**
     * @return
     * @throws com.anite.zebra.core.exceptions.DefinitionNotFoundException
     */
    public ITaskDefinition getTaskDefinition()
            throws DefinitionNotFoundException {
        return taskInstance.getTaskDefinition();
    }
    /**
     * @return
     */
    public Long getTaskInstanceId() {
        return taskInstance.getTaskInstanceId();
    }
    /**
     * @return
     */
    public User getTaskOwner() {
        return taskInstance.getTaskOwner();
    }
    /* (non-Javadoc)
     * @see java.lang.Object#hashCode()
     */
    public int hashCode() {
        return taskInstance.hashCode();
    }
    /**
     * @param actualCompletionDate
     */
    public void setActualCompletionDate(Date actualCompletionDate) {
        taskInstance.setActualCompletionDate(actualCompletionDate);
    }
    /**
     * @param caption
     */
    public void setCaption(String caption) {
        taskInstance.setCaption(caption);
    }
    /**
     * @param dateCreated
     */
    public void setDateCreated(Date dateCreated) {
        taskInstance.setDateCreated(dateCreated);
    }
    /**
     * @param dateDue
     */
    public void setDateDue(Date dateDue) {
        taskInstance.setDateDue(dateDue);
    }
    /**
     * @param decisionMadeBy
     */
    public void setDecisionMadeBy(User decisionMadeBy) {
        taskInstance.setDecisionMadeBy(decisionMadeBy);
    }
    /**
     * @param foe
     */
    public void setFOE(IFOE foe) {
        taskInstance.setFOE(foe);
    }
    /**
     * @param processInstance
     */
    public void setProcessInstance(AntelopeProcessInstance processInstance) {
        taskInstance.setProcessInstance(processInstance);
    }
    /**
     * @param propertySetEntries
     */
    public void setPropertySetEntries(Map propertySetEntries) {
        taskInstance.setPropertySet(propertySetEntries);
    }
    /**
     * @param routingAnswer
     */
    public void setRoutingAnswer(String routingAnswer) {
        taskInstance.setRoutingAnswer(routingAnswer);
    }
    /**
     * @param state
     */
    public void setState(long state) {
        taskInstance.setState(state);
    }
    /**
     * @param taskDefinition
     */
    public void setTaskDefinition(AntelopeTaskDefinition taskDefinition) {
        taskInstance.setTaskDefinition(taskDefinition);
    }
    /**
     * @param taskInstanceId
     */
    public void setTaskInstanceId(Long taskInstanceId) {
        taskInstance.setTaskInstanceId(taskInstanceId);
    }
    /**
     * @param user
     */
    public void setTaskOwner(User user) {
        taskInstance.setTaskOwner(user);
    }
    /* (non-Javadoc)
     * @see java.lang.Object#toString()
     */
    public String toString() {
        return taskInstance.toString();
    }
 
    /**
     * @return Returns the taskInstance.
     */
    public AntelopeTaskInstance getTaskInstance() {
        return taskInstance;
    }
}