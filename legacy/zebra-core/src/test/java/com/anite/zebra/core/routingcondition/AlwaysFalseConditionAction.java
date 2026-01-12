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

package com.anite.zebra.core.routingcondition;

import com.anite.zebra.core.api.IConditionAction;
import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.exceptions.RunRoutingException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Test routing condition action that always returns FALSE
 * 
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class AlwaysFalseConditionAction implements IConditionAction {

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.api.IConditionAction#runCondition(com.anite.zebra.core.definitions.api.IRoutingDefinition, com.anite.zebra.core.state.api.ITaskInstance)
	 */
	public boolean runCondition(IRoutingDefinition routingDef,
			ITaskInstance taskInstance) throws RunRoutingException {
		return false;
	}

}
