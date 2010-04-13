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

package uk.co.gidley.zebra.service.om.definitions;

import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinitions;

import java.util.Iterator;
import java.util.Set;

/**
 * @author Eric Pugh
 */
public class TaskDefinitions implements ITaskDefinitions {

	private Set taskDefinitions = null;

	private TaskDefinitions() {

	}

	public TaskDefinitions(Set taskDefinitions) {
		this.taskDefinitions = taskDefinitions;
	}

	/**
	 * @param id
	 * @return
	 */
	public ITaskDefinition getTaskDef(Long id) {
		ITaskDefinition taskDef = null;
		for (Iterator i = taskDefinitions.iterator(); i.hasNext();) {
			ITaskDefinition td = (ITaskDefinition) i.next();
			if (td.getId().equals(id)) {
				taskDef = td;
				break;
			}
		}
		return taskDef;
	}

	public Iterator iterator() {
		return taskDefinitions.iterator();
	}

}