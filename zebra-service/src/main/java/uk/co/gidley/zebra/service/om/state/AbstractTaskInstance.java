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

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.ITaskInstance;
import org.apache.commons.lang.exception.NestableRuntimeException;
import uk.co.gidley.zebra.service.om.definitions.TaskDefinition;

import javax.persistence.Basic;
import javax.persistence.CascadeType;
import javax.persistence.Column;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.ManyToOne;
import javax.persistence.MappedSuperclass;
import java.util.Date;

/**
 * Abstract class for both Historical and Current task instances. It is done this way to keep them in seperate tables as
 * that is useful.
 *
 * @author Matthew.Norris
 * @author Ben Gidley
 */
@MappedSuperclass
public abstract class AbstractTaskInstance implements ITaskInstance {

	/* Properties for implementing the interface */
	private IFOE FOE;

	private ProcessInstance processInstance;

	private long state;

	private Long taskInstanceId;

	private Priority priority;

	/* Custom Properties */

	private String routingAnswer;

	private String caption;

	private String description;

	private String outcome;

	private Date dateDue;

	private Date dateCreated;

	private Date actualCompletionDate;

	private Long taskDefinitionId;

	/**
	 * Boolean used to decide if this should be shown on any task list (set by factory)
	 */
	private boolean showInTaskList;

	public Long getTaskDefinitionId() {
		return taskDefinitionId;
	}

	public void setTaskDefinitionId(Long taskDefinitionId) {
		this.taskDefinitionId = taskDefinitionId;
	}

	public AbstractTaskInstance() {
		//noop
	}

	/**
	 * Copy constructor Sets all fields EXCEPT for the instanceId
	 *
	 * @param taskInstance a task instance
	 */
	public AbstractTaskInstance(AbstractTaskInstance taskInstance) {
		/* Standard Properties */
		setFOE(taskInstance.getFOE());
		setState(taskInstance.getState());
		setProcessInstance(taskInstance.getProcessInstance());
		setTaskDefinitionId(taskInstance.getTaskDefinitionId());

		setRoutingAnswer(taskInstance.getRoutingAnswer());
		setCaption(taskInstance.getCaption());
		setDateDue(taskInstance.getDateDue());
		setDateCreated(taskInstance.getDateCreated());
		setActualCompletionDate(taskInstance.getActualCompletionDate());
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
	 * @param taskInstanceId The taskInstanceId to set.
	 */
	public void setTaskInstanceId(Long taskInstanceId) {
		this.taskInstanceId = taskInstanceId;
	}

	@ManyToOne(targetEntity = ProcessInstance.class, cascade = { CascadeType.MERGE, CascadeType.PERSIST })
	public ProcessInstance getProcessInstance() {
		return this.processInstance;
	}

	public void setProcessInstance(ProcessInstance processInstance) {
		this.processInstance = processInstance;
	}

	@Basic
	public long getState() {
		return this.state;
	}

	public void setState(long newState) {
		this.state = newState;
	}

	@ManyToOne(targetEntity = FOE.class, cascade = { CascadeType.PERSIST, CascadeType.MERGE })
	public IFOE getFOE() {
		return this.FOE;
	}

	public void setFOE(IFOE foe) {
		this.FOE = foe;
	}

	@Basic
	public String getRoutingAnswer() {
		return this.routingAnswer;
	}

	public void setRoutingAnswer(String routingAnswer) {
		this.routingAnswer = routingAnswer;
	}

	@Basic
	public String getCaption() {
		try {
			if (this.caption == null && this.getTaskDefinition() != null) {
				this.caption = ((TaskDefinition) this.getTaskDefinition()).getName();
			}
			return this.caption;
		} catch (DefinitionNotFoundException e) {
			throw new NestableRuntimeException(e);
		}
	}

	public void setCaption(String caption) {
		this.caption = caption;
	}

	@Basic
	public Date getDateCreated() {
		return this.dateCreated;
	}

	public void setDateCreated(Date dateCreated) {
		this.dateCreated = dateCreated;
	}

	@Basic
	public Date getDateDue() {
		return this.dateDue;
	}

	public void setDateDue(Date dateDue) {
		this.dateDue = dateDue;
	}

	@Basic
	public Date getActualCompletionDate() {
		return this.actualCompletionDate;
	}

	/**
	 * sets the "actual" completion date for the task; this is in addition to the completion date that is automatically
	 * set
	 */
	public void setActualCompletionDate(Date actualCompletionDate) {
		this.actualCompletionDate = actualCompletionDate;
	}

	@Basic
	public boolean isShowInTaskList() {
		return this.showInTaskList;
	}

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
	 * @param priority The priority to set.
	 */
	public void setPriority(Priority priority) {
		this.priority = priority;
	}

	/**
	 * This is the detailed description of this step - this is not used by the engine but may be useful for example for
	 * showing in the history
	 *
	 * @return Returns the description.
	 */
	@Basic
	@Column(length = 4000)
	public String getDescription() {
		return this.description;
	}

	/**
	 * @param description The description to set.
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
	 * @param outcome The outcome to set.
	 */
	public void setOutcome(String outcome) {
		this.outcome = outcome;
	}

	public ITaskDefinition getTaskDefinition() throws DefinitionNotFoundException {
		return null;
	}
}