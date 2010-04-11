/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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
package com.anite.zebra.core.definitions;

import junit.framework.Assert;

import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.routingcondition.MockRoutingCondition;

/**
 * @author Matthew Norris
 * Created on 19-Aug-2005
 *
 */
public class MockRouting implements IRoutingDefinition {
	private static long idCounter = 1;
	private ITaskDefinition destinationTaskDefinition;
	private ITaskDefinition originatingTaskDefinition;
	private String conditionClass;
	private boolean parallel;
	private String name;
	private Long id;

	public MockRouting(MockTaskDef source, MockTaskDef dest) {
		MockProcessDef pd = source.getProcessDef();
		Assert.assertTrue(pd.equals(dest.getProcessDef()));
		this.id = new Long(idCounter++);
		pd.getMockRoutingDefs().add(this);
		source.getRoutingOut().add(this);
		dest.getRoutingIn().add(this);
		this.destinationTaskDefinition = dest;
		this.originatingTaskDefinition = source;
		this.conditionClass = MockRoutingCondition.class.getName();
		
	}
	
	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getId()
	 */
	public Long getId() {
		return id;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getName()
	 */
	public String getName() {
		return name;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getParallel()
	 */
	public boolean getParallel() {
		return parallel;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getConditionClass()
	 */
	public String getConditionClass() {
		return conditionClass;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getOriginatingTaskDefinition()
	 */
	public ITaskDefinition getOriginatingTaskDefinition() {
		return originatingTaskDefinition;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinition#getDestinationTaskDefinition()
	 */
	public ITaskDefinition getDestinationTaskDefinition() {
		return destinationTaskDefinition;
	}

	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @param b
	 */
	public void setParallel(boolean parallel) {
		this.parallel = parallel;
	}

	public void setName(String name) {
		this.name = name;
	}

	public void setConditionClass(String conditionClass) {
		this.conditionClass = conditionClass;
	}

}
