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

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.IProcessInstance;
import org.apache.commons.lang.exception.NestableException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.persistence.Basic;
import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.ManyToOne;
import javax.persistence.OneToMany;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * A Zebra Process Instance reflect an instance of a Process Definition. This class implements the core interface and
 * add additional properties as commonly required by the applications This class can be extended, but this should not be
 * necessary.
 * <p/>
 * This implementation supports subflows and dynamic workflow security.
 * <p/>
 *
 * @author Matthew.Norris
 * @author Ben Gidley
 */
@Entity
public class ProcessInstance implements IProcessInstance {

	private static Logger log = LoggerFactory.getLogger(ProcessInstance.class);

	/* Field Variables for Interface */
	private Long processDefinitionId;

	private Long processInstanceId = null;

	private long state;

	private Set<TaskInstance> taskInstances = new HashSet<TaskInstance>();

	/* Custom behavioural properties */
	/**
	 * Parent Process used for subflows
	 */
	private ProcessInstance parentProcessInstance;

	/**
	 * Task instance from parent for subflow step
	 */
	private TaskInstance parentTaskInstance;

	/* Custom Informational Properties */
	/**
	 * The user friendly name of this process
	 */
	private String processName;


	/**
	 * The property set catch all for anything at all
	 */
	private Map<String, PropertySetEntry> propertySet = new HashMap<String, PropertySetEntry>();

	/**
	 * Set of historical task instance information
	 */
	private Set<TaskInstanceHistory> historyInstances = new HashSet<TaskInstanceHistory>();

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
	private Set<FOE> fOES = new HashSet<FOE>();

	/**
	 * Default constructor for normal construction
	 */
	public ProcessInstance() {
		// noop
	}

	/**
	 * constructor from another instance (e.g. for history)
	 *
	 * @param processInstance AntelopeProcessInstance
	 */
	public ProcessInstance(ProcessInstance processInstance) throws NestableException {
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
	 * @param processDefinitionId The processDefinitionId to set.
	 */
	public void setProcessDefinitionId(Long processDefinitionId) {
		this.processDefinitionId = processDefinitionId;
	}

	/**
	 * @return Returns the fOEs.
	 */
	public Set<FOE> getFOEs() {
		return this.fOES;
	}

	/**
	 * @param es The fOEs to set.
	 */
	public void setFOEs(Set<FOE> es) {
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
	 * @param relatedClass The relatedClass to set.
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
	 * @param relatedKey The relatedKey to set.
	 */
	public void setRelatedKey(Long relatedKey) {
		this.relatedKey = relatedKey;
	}

	/* IProcessInstance Methods */

	/**
	 * Interface method for get the Process definition Note this should never actually throw definition not found exception
	 * as that would imply this instance can't exist. Which it does!
	 */
	public IProcessDefinition getProcessDef() throws DefinitionNotFoundException {
//
//        ZebraDefinitionFactory definitons = (ZebraDefinitionFactory) RegistryManager.getInstance().getRegistry()
//                .getService("zebra.zebraDefinitionFactory", ZebraDefinitionFactory.class);
//        return definitons.getProcessDefinitionById(this.processDefinitionId);

		// TODO reimplement
		return null;
	}

	/**
	 * This the unique ID of the process in the database
	 *
	 * @return Returns the processInstanceId.
	 */
	public Long getProcessInstanceId() {
		return this.processInstanceId;
	}

	/**
	 * @param processInstanceId The processInstanceId to set.
	 */
	public void setProcessInstanceId(Long processInstanceId) {
		this.processInstanceId = processInstanceId;
	}

	/**
	 * This is the state constant defined in Zebra
	 */
	public long getState() {
		return this.state;
	}

	public void setState(long newState) {
		this.state = newState;
	}

	/**
	 * @return
	 */
	public Set<TaskInstance> getTaskInstances() {
		return this.taskInstances;
	}

	public void setTaskInstances(Set<TaskInstance> taskInstances) {
		this.taskInstances = taskInstances;
	}

	/**
	 * @return Returns the parentProcessInstance.
	 */
	public ProcessInstance getParentProcessInstance() {
		return this.parentProcessInstance;
	}

	/**
	 * @param parentProcessInstance The parentProcessInstance to set.
	 */
	public void setParentProcessInstance(ProcessInstance parentProcessInstance) {
		this.parentProcessInstance = parentProcessInstance;
	}

	/**
	 * The process property set.
	 * <p/>
	 * This is a set of ZebraProperty Set Entry objects. These in turn can hold almost anythings
	 * <p/>
	 * You can easily introduce performance issues by putting too much in here! Real data should reside in a related table.
	 * This should ONLY hold items needed to process the flow.
	 * <p/>
	 * Items in here are effectively disposed of when the flow ends.
	 * <p/>
	 * Items are only passed back and forth from subflows if explictly marked to do so in the designer. For those used to
	 * earlier versions of zebra push outputs has been removed.
	 *
	 * @return
	 */
	public Map<String, PropertySetEntry> getPropertySet() {
		return this.propertySet;
	}

	public void setPropertySet(Map<String, PropertySetEntry> propertySetEntries) {
		this.propertySet = propertySetEntries;
	}

	/**
	 * A helper function to ensure the referential integrity in maintained
	 *
	 * @param key
	 * @param entry
	 */
	public void addPropertySetEntry(String key, PropertySetEntry entry) {
		entry.setKey(key);
		entry.setProcessInstance(this);
		this.getPropertySet().put(key, entry);
	}

	/**
	 * Remove item from the property set
	 *
	 * @param key
	 */
	public void removePropertySetEntry(String key) {
		PropertySetEntry entry = this.getPropertySet().get(key);
		if (entry != null) {
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
	 * @param processName The processName to set.
	 */
	public void setProcessName(String processName) {
		this.processName = processName;
	}

	/**
	 * @return
	 */
	@OneToMany(fetch = FetchType.LAZY, cascade = { CascadeType.ALL })
	public Set<TaskInstanceHistory> getHistoryInstances() {
		return this.historyInstances;
	}

	public void setHistoryInstances(Set<TaskInstanceHistory> historyInstances) {
		this.historyInstances = historyInstances;
	}

	@ManyToOne(targetEntity = TaskInstance.class)
	public TaskInstance getParentTaskInstance() {
		return this.parentTaskInstance;
	}

	/**
	 * @param parentTaskInstance The parentTaskInstance to set.
	 */
	public void setParentTaskInstance(TaskInstance parentTaskInstance) {
		this.parentTaskInstance = parentTaskInstance;
	}
}