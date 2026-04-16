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

import com.anite.antelope.utils.CalendarHelper;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;

/**
 * @author Matthew.Norris
 * @author Ben Gidley
 * @hibernate.class
 * @hibernate.cache usage="transactional"
 */
public class AntelopeTaskInstanceHistory extends AbstractAntelopeTaskInstance {

    private Date dateCompleted;

    private Boolean showInHistory;

    /**
     * Default Constructor
     */
    public AntelopeTaskInstanceHistory() {
        // default constructor - need this so object can be instantiated as part of a query
    }

    /**
     * constructor used when creating a new history entry. 
     * @param instance
     */
    public AntelopeTaskInstanceHistory(AbstractAntelopeTaskInstance taskInstance)
            throws DefinitionNotFoundException {
        super(taskInstance);
        setDateCompleted(CalendarHelper.getInstance().getDateTimeNow());

        if (this.getDecisionMadeBy() == null) {
            this.setDecisionMadeBy(this.getTaskOwner());
        }
        if (this.getOutcome() == null) {
            this.setOutcome(AbstractAntelopeTaskInstance.COMPLETED);
        }
    }

    /**
     * @hibernate.property
     * @return Returns the dateCompleted.
     */
    public Date getDateCompleted() {
        return dateCompleted;
    }

    /**
     * get the date completed in string format
     * @return
     */
    public String getStringDateComplete() {
        if (dateCompleted != null) {
            return CalendarHelper.getInstance().getFormattedDate(dateCompleted);
        }
        return "";

    }

    /**
     * @param dateCompleted The dateCompleted to set.
     */
    public void setDateCompleted(Date dateCompleted) {
        this.dateCompleted = dateCompleted;
    }

    /**
     * when set to true, the task will not be shown in the task history
     * 
     * @hibernate.property not-null="true"
     * @return Returns the showInHistory.
     */
    public Boolean getShowInHistory() {
        return showInHistory;
    }

    /**
     * @param showInHistory The showInHistory to set.
     */
    public void setShowInHistory(Boolean showInHistory) {
        this.showInHistory = showInHistory;
    }

}