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
 * @author Matthew.Norris
 */
public class RoutingNameCondition implements IConditionAction {
    private static Log log = LogFactory.getLog(RoutingNameCondition.class);

    /**
     * Run the condition if and only if it is an AntelopeTaskInstance
     */
    public boolean runCondition(IRoutingDefinition routingDef,
            ITaskInstance taskInstance) throws RunRoutingException {
        ZebraTaskInstance antelopeTaskInstance;
        try {
            antelopeTaskInstance = (ZebraTaskInstance) taskInstance;
        } catch (Exception e) {
            log.error(e);
            throw new RunRoutingException(e);
        }
        return runCondition(routingDef, antelopeTaskInstance);
    }

    /**
     * Match the string in getRoutingAnswer to the name of the routing definition
     * 
     * @param routingDef
     * @param taskInstance
     * @return
     * @throws RunRoutingException
     */
    public boolean runCondition(IRoutingDefinition routingDef,
            ZebraTaskInstance taskInstance) throws RunRoutingException {
        if (routingDef.getName() == null) {
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
        if (log.isDebugEnabled()) {
            log.debug("Comparing \"" + taskInstance.getRoutingAnswer()
                    + "\" to \"" + routingDef.getName() + "\"");
        }
        return (taskInstance.getRoutingAnswer().equalsIgnoreCase(routingDef
                .getName()));
    }

}