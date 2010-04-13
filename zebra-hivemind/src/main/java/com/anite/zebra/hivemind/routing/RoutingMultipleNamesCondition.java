/*
 * Copyright 2004 Anite - Central Government Division
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

package com.anite.zebra.hivemind.routing;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.api.IConditionAction;
import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.exceptions.RunRoutingException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * Run routing if the instance routing answer contains the routing answer can
 * handle multiple successful routings using ';' as a seperator.
 * 
 * @author Ben.Gidley
 */
public class RoutingMultipleNamesCondition implements IConditionAction {

	private final static Log log = LogFactory
			.getLog(RoutingMultipleNamesCondition.class);

	/*
	 * (non-Javadoc)
	 * 
	 * @see com.anite.zebra.core.api.IConditionAction#runCondition(com.anite.zebra.core.definitions.api.IRoutingDefinition,
	 *      com.anite.zebra.core.state.api.ITaskInstance)
	 */
	public boolean runCondition(IRoutingDefinition routingDefinition,
			ITaskInstance taskInstance) throws RunRoutingException {
		return runCondition(routingDefinition, (ZebraTaskInstance) taskInstance);
	}

	public boolean runCondition(IRoutingDefinition routingDefinition,
			ZebraTaskInstance taskInstance) {

		if (routingDefinition.getName() == null) {
			if (log.isWarnEnabled()) {
				log.warn("RoutingDef name is null" + taskInstance.getCaption());
			}
			return true;
		}
		if (taskInstance.getRoutingAnswer() == null) {
			if (log.isWarnEnabled()) {
				log.warn("HibernateTaskInstance answer is null: "
						+ taskInstance.getCaption());
			}
			return false;
		}

		String name = routingDefinition.getName();
		String[] answers = taskInstance.getRoutingAnswer().split(";");
		for (int i = 0; i < answers.length; i++) {
			if (answers[i].equalsIgnoreCase(name)) {
				return true;
			}
		}

		return false;
	}

}
