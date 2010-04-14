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

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;

import javax.persistence.CascadeType;
import javax.persistence.Entity;
import javax.persistence.FetchType;
import javax.persistence.MapKey;
import javax.persistence.OneToMany;
import java.util.HashMap;
import java.util.Map;

/**
 * This represents a currently running task Instance.
 * <p/>
 * The primary addition is a the propertySet for runtime properties. These are disposted on when this moves into the
 * history
 *
 * @author Ben.Gidley
 */
@Entity
public class TaskInstance extends AbstractTaskInstance {

	public static final long KILLED = 66;

	/**
	 * The property set catch all for anything at all It will be emptied when the history item is constructed
	 */
	private Map<String, PropertySetEntry> propertySet = new HashMap<String, PropertySetEntry>();

	/**
	 * Default Constructor
	 */
	public TaskInstance() {
		super();
	}

	/**
	 * Copy Constructor
	 *
	 * @param taskInstance
	 * @throws DefinitionNotFoundException
	 */
	public TaskInstance(AbstractTaskInstance taskInstance) {
		super(taskInstance);

	}

	/**
	 * The property set. This is a catch all container for run time property information. If you make this too big (>64k
	 * from WFMC recommendations) it will slow the system down and potentially cause interoperability issues. Please store
	 * any sizable data elsewhere.
	 *
	 * @return
	 */
	@OneToMany(cascade = CascadeType.ALL, mappedBy = "taskInstance", fetch = FetchType.LAZY)
	@MapKey(name = "key")
	public Map<String, PropertySetEntry> getPropertySet() {
		return this.propertySet;
	}

	/**
	 * A helper function to ensure the referential integrity in maintained
	 *
	 * @param key
	 * @param entry
	 */
	public void addPropertySetEntry(String key, PropertySetEntry entry) {
		entry.setKey(key);
		entry.setTaskInstance(this);
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
			entry.setTaskInstance(null);
		}
		this.getPropertySet().remove(key);

	}

	/**
	 * @param propertySetEntries The propertySetEntries to set.
	 */
	public void setPropertySet(
			Map<String, PropertySetEntry> propertySetEntries) {
		this.propertySet = propertySetEntries;
	}

	@Override
	public String toString() {
		if (this.getTaskInstanceId() != null) {
			return this.getTaskInstanceId().toString();
		} else {
			return "New instance of TD:" + this.getTaskDefinitionId();
		}
	}
}
