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

import com.anite.zebra.core.definitions.api.IRoutingDefinition;

/**
 * @author Eric Pugh
 * @hibernate.class
 */
public class RoutingDefinition implements IRoutingDefinition {

	private Long id;

	private TaskDefinition originatingTaskDefinition;

	private TaskDefinition destinationTaskDefinition;

	private String name;

	private boolean parallel;

	private String conditionClass;


	public Long getId() {
		return id;
	}


	public String getName() {
		return this.name;
	}

	public void setName(String name) {
		this.name = name;
	}

	public boolean getParallel() {
		return this.parallel;
	}

	public void setParallel(boolean parallel) {
		this.parallel = parallel;
	}

	public String getConditionClass() {
		return this.conditionClass;
	}

	public void setConditionClass(String conditionClass) {
		this.conditionClass = conditionClass;
	}

	public TaskDefinition getDestinationTaskDefinition() {
		return destinationTaskDefinition;
	}

	public void setDestinationTaskDefinition(TaskDefinition destinationTaskDefinition) {
		this.destinationTaskDefinition = destinationTaskDefinition;
	}

	public TaskDefinition getOriginatingTaskDefinition() {
		return originatingTaskDefinition;
	}

	public void setOriginatingTaskDefinition(TaskDefinition originatingTaskDefinition) {
		this.originatingTaskDefinition = originatingTaskDefinition;
	}

}