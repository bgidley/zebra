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

package uk.co.gidley.zebra.service.services;

import uk.co.gidley.zebra.service.om.definitions.ProcessDefinition;
import uk.co.gidley.zebra.service.om.definitions.TaskDefinition;

import java.util.List;

/**
 * provides access to stored process definitions
 * <p/>
 * This interface deliberately doesn't worry about how these got created.
 * <p/>
 * Created by IntelliJ IDEA. User: ben Date: Apr 13, 2010 Time: 8:14:00 AM
 */
public interface ProcessDefinitionFactory {
	public TaskDefinition getTaskDefinition(Long id);

	/**
	 * Find the process with given name within the named process
	 *
	 * @param processName
	 * @param taskName
	 * @return
	 */
	public List<Long> getTaskDefinitionIds(String processName, String taskName);

	public ProcessDefinition getProcessDefinitionById(Long id);

	public ProcessDefinition getProcessDefinitionByName(String name);
}
