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

import javax.persistence.Entity;
import java.io.Serializable;

/**
 * @author Matthew.Norris
 * @author Ben Gidley
 * @author John Rae
 */
@Entity
public class PropertySetEntry {

	private Integer propertySetId;

	private TaskInstance taskInstance;

	private ProcessInstance processInstance;

	private String value = null;

	private String key = null;

	private Serializable object = null;

	public ProcessInstance getProcessInstance() {
		return processInstance;
	}

	public void setProcessInstance(ProcessInstance processInstance) {
		this.processInstance = processInstance;
	}

	public TaskInstance getTaskInstance() {
		return taskInstance;
	}

	public void setTaskInstance(TaskInstance taskInstance) {
		this.taskInstance = taskInstance;
	}

	public PropertySetEntry() {
		//noop
	}

	/**
	 * Constructor taking String
	 *
	 * @param value
	 */
	public PropertySetEntry(String value) {
		setValue(value);
	}

	/**
	 * Constructor taking Object
	 *
	 * @param object
	 */
	public PropertySetEntry(Serializable object) {
		setObject(object);
	}


	public String getValue() {
		return this.value;
	}

	/**
	 * @param value The value to set.
	 */
	public void setValue(String value) {
		this.value = value;
	}

	/**
	 * This is a serialized object. 100k is the max length here but in many databases hibernate will pick a bigger type.
	 * <p/>
	 * In oracle this is created as a long raw. Many DBA's will tell you this is bad. They are right (Blobs could be
	 * better) and wrong (Oracle JDBC does not support this sufficently). Unfortunately Oracle BLOB support is too
	 * different from other JDBC drivers for it to work here.
	 *
	 * @return Returns the object.
	 */
	public Serializable getObject() {
		return this.object;
	}

	/**
	 * @param object The object to set.
	 */
	public void setObject(Serializable object) {
		this.object = object;
	}

	public Integer getPropertySetId() {
		return propertySetId;
	}

	public void setPropertySetId(Integer propertySetId) {
		this.propertySetId = propertySetId;
	}

	public String getKey() {
		return key;
	}

	public void setKey(String key) {
		this.key = key;
	}

}