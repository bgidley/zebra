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

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;

import java.util.HashSet;
import java.util.Set;

/**
 * Created by IntelliJ IDEA. User: ben Date: Apr 13, 2010 Time: 8:28:38 AM
 */
public class ProcessDefinition implements IProcessDefinition {

	private Long id;

	private Set<TaskDefinition> taskDefinitions = new HashSet<TaskDefinition>();

	private Set routingDefinitions = new HashSet();

	private TaskDefinition firstTask = null;

	private String classConstruct = null;

	private String classDestruct = null;

	private Long version;

	private ProcessVersions processVersions;

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public Set<TaskDefinition> getTaskDefinitions() {
		return taskDefinitions;
	}

	public void setTaskDefinitions(Set<TaskDefinition> taskDefinitions) {
		this.taskDefinitions = taskDefinitions;
	}

	public Set getRoutingDefinitions() {
		return routingDefinitions;
	}

	public void setRoutingDefinitions(Set routingDefinitions) {
		this.routingDefinitions = routingDefinitions;
	}

	public ITaskDefinition getFirstTask() {
		return firstTask;
	}

	public void setFirstTask(TaskDefinition firstTask) {
		this.firstTask = firstTask;
	}

	public String getClassConstruct() {
		return classConstruct;
	}

	public void setClassConstruct(String classConstruct) {
		this.classConstruct = classConstruct;
	}

	public String getClassDestruct() {
		return classDestruct;
	}

	public void setClassDestruct(String classDestruct) {
		this.classDestruct = classDestruct;
	}

	public Long getVersion() {
		return version;
	}

	public void setVersion(Long version) {
		this.version = version;
	}

	public ProcessVersions getProcessVersions() {
		return processVersions;
	}

	public void setProcessVersions(ProcessVersions processVersions) {
		this.processVersions = processVersions;
	}

	public TaskDefinitions getTaskDefs() {
		return new TaskDefinitions(taskDefinitions);
	}

	public RoutingDefinitions getRoutingDefs() {
		return new RoutingDefinitions(routingDefinitions);
	}
}
