/*
 * Original Code Copyright 2004, 2005 Anite - Central Government Division
 * http://www.anite.com/publicsector
 *
 * Modifications Copyright 2010 Ben Gidley
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */

package uk.co.gidley.zebra.service.om.state;

import javax.persistence.Basic;
import javax.persistence.Entity;
import java.util.Calendar;
import java.util.Date;

/**
 * A object representing a completed task. This is created once the task has been completed
 *
 * @author Matthew.Norris
 * @author Ben Gidley
 */
@Entity
public class TaskInstanceHistory extends AbstractTaskInstance {

	private Date dateCompleted;

	private Boolean showInHistory;

	/**
	 * Default Constructor
	 */
	public TaskInstanceHistory() {
		// default constructor - need this so object can be instantiated as part
		// of a query
	}

	/**
	 * constructor used when creating a new history entry.
	 */
	public TaskInstanceHistory(AbstractTaskInstance taskInstance) {
		super(taskInstance);
		setDateCompleted(Calendar.getInstance().getTime());
	}

	/**
	 * @return Returns the dateCompleted.
	 */
	@Basic
	public Date getDateCompleted() {
		return this.dateCompleted;
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
	 * @return Returns the showInHistory.
	 */
	@Basic
	public Boolean getShowInHistory() {
		return this.showInHistory;
	}

	/**
	 * @param showInHistory The showInHistory to set.
	 */
	public void setShowInHistory(Boolean showInHistory) {
		this.showInHistory = showInHistory;
	}

}