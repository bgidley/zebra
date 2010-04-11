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

package com.anite.antelope.zebra.processLifecycle;

import java.io.Serializable;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.entity.User;

import com.anite.antelope.zebra.om.Priority;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;


/**
 * This represent data for a task instance that has been set in advance
 * Such as caption and the like
 * 
 * It will be used in preferce to design time properties if placed in the process
 * property set under the key of the of the
 * 
 * This uses the primary keys internally of a lot of things to avoid hibernate issues
 *  
 * @author Ben.Gidley
 */
public class AntelopeTaskInstancePresets implements Serializable {
    private final static Log log = LogFactory
            .getLog(AntelopeTaskInstancePresets.class);

    private Long taskOwnerUserId;

    private String caption;

    private Long priorityId;

    private String description;

    private Date dateDue;

    private Date dateCreated;

    private Date actualCompletionDate;

    private Long userIdDecisionMadeBy;
    
    
    private Map propertySet = new HashMap();

    public Map getPropertySet() {
        return propertySet;
    }
    public void setPropertySet(Map propertySet) {
        this.propertySet = propertySet;
    }
    /**
     * @return Returns the actualCompletionDate.
     */
    public Date getActualCompletionDate() {
        return actualCompletionDate;
    }

    /**
     * @param actualCompletionDate The actualCompletionDate to set.
     */
    public void setActualCompletionDate(Date actualCompletionDate) {
        this.actualCompletionDate = actualCompletionDate;
    }

    /**
     * @return Returns the caption.
     */
    public String getCaption() {
        return caption;
    }

    /**
     * @param caption The caption to set.
     */
    public void setCaption(String caption) {
        this.caption = caption;
    }

    /**
     * @return Returns the dateCreated.
     */
    public Date getDateCreated() {
        return dateCreated;
    }

    /**
     * @param dateCreated The dateCreated to set.
     */
    public void setDateCreated(Date dateCreated) {
        this.dateCreated = dateCreated;
    }

    /**
     * @return Returns the dateDue.
     */
    public Date getDateDue() {
        return dateDue;
    }

    /**
     * @param dateDue The dateDue to set.
     */
    public void setDateDue(Date dateDue) {
        this.dateDue = dateDue;
    }

    /**
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
     * @return Returns the priorityId.
     */
    public Priority getPriority() {
        Session session;
        try {
            if (priorityId != null) {
                session = PersistenceLocator.getInstance().getCurrentSession();
                return (Priority) session.load(Priority.class, priorityId);
            } else {
                return null;
            }
        } catch (PersistenceException e) {
            log.error("Failed to reload a priority", e);
            throw new RuntimeException(e);
        } catch (HibernateException e) {
            log.error("Failed to reload a priority", e);
            throw new RuntimeException(e);
        }
    }

    /**
     * @param priorityId The priorityId to set.
     */
    public void setPriority(Priority priority) {
        this.priorityId = priority.getPriorityId();
    }

    /**
     * @return Returns the userId.
     */
    public User getTaskOwner() {
        Session session;
        try {
            if (taskOwnerUserId != null) {
                session = PersistenceLocator.getInstance().getCurrentSession();
                return (User) session.load(User.class, taskOwnerUserId);
            } else {
                return null;
            }
        } catch (PersistenceException e) {
            log.error("Failed to reload a user", e);
            throw new RuntimeException(e);
        } catch (HibernateException e) {
            log.error("Failed to reload a user", e);
            throw new RuntimeException(e);
        }
    }

    /**
     * @param userId The userId to set.
     */
    public void setTaskOwner(User user) {
        this.taskOwnerUserId = (Long) user.getId();
    }

    /**
     * @return Returns the userIdDecisionMadeBy.
     */
    public User getDecisionMadeBy() {
        Session session;
        try {
            if (userIdDecisionMadeBy != null) {
                session = PersistenceLocator.getInstance().getCurrentSession();
                return (User) session.load(User.class, userIdDecisionMadeBy);
            } else {
                return null;
            }
        } catch (PersistenceException e) {
            log.error("Failed to reload a user", e);
            throw new RuntimeException(e);
        } catch (HibernateException e) {
            log.error("Failed to reload a user", e);
            throw new RuntimeException(e);
        }
    }

    /**
     * @param userIdDecisionMadeBy The userIdDecisionMadeBy to set.
     */
    public void setUserIdDecisionMadeBy(User userDecisionMadeBy) {
        this.userIdDecisionMadeBy = (Long) userDecisionMadeBy.getId();
    }

    /**
     * @param priorityId The priorityId to set.
     */
    public void setPriorityId(Long priorityId) {
        this.priorityId = priorityId;
    }
    
}