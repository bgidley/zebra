/*
 * Copyright 2004/2005 Anite - Enforcement & Security
 * http://www.anite.com/publicsector
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
package com.anite.zebra.core.util;

import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * This helper class contains the task synchronisation code. It's only called by
 * the Engine.
 * 
 * @author Matthew.Norris
 */
public class TaskSync {
    private static Log log = LogFactory.getLog(TaskSync.class);
	/**
     * @return Returns TaskDefs marked as Synchronise=TRUE that this TaskDef can
     *         potentially block
     */
    public Map getPotentialTaskLocks(ITaskDefinition taskDef) {
        /*
         * iterate through all outbound routes from this TaskDef, looking for
         * TaskDefs with sync=TRUE and return them.
         */
        Map syncTasks = new HashMap();
        Map visited = new HashMap();
        Map toCheck = new HashMap();
        toCheck.put(taskDef.getId(), taskDef);
        while (!toCheck.isEmpty()) {
            ITaskDefinition td = (ITaskDefinition) ((Map.Entry) toCheck.entrySet().toArray()[0]).getValue();
            visited.put(td.getId(), td);
            for (Iterator it = td.getRoutingOut().iterator(); it.hasNext();) {
                IRoutingDefinition rd = (IRoutingDefinition)it.next();
                ITaskDefinition checkTask = rd.getDestinationTaskDefinition();
                if (checkTask.isSynchronised()) {
                    // is a sync task
                    if (!syncTasks.containsKey(checkTask.getId())) {
                        syncTasks.put(checkTask.getId(), checkTask);
                    }
                }
                /*
                 * even if we find a sync task we need to keep looking as there
                 * may be more further down the chain that we can block
                 */
                if (!toCheck.containsKey(checkTask.getId())) {
                    // not already in the "check" list
                    if (!visited.containsKey(checkTask.getId())) {
                        // not already visited
                        toCheck.put(checkTask.getId(), checkTask);
                    }
                }
            }
            toCheck.remove(td.getId());
        }
        return syncTasks;
    }

    /**
     * returns true if the specified task instance is blocked by other active
     * tasks on the processinstance
     * 
     * @param task
     * @return
     */
    public boolean isTaskBlocked(ITaskInstance task) throws DefinitionNotFoundException {
        Set processTasks = task.getProcessInstance().getTaskInstances();
        /*
         * build up a unique list of task definitions from the currently running
         * tasks - these are all potential blockers
         */
        Map blockingDefs = new HashMap();
        for (Iterator it = processTasks.iterator(); it.hasNext();) {
            ITaskInstance iti = (ITaskInstance) it.next();
            if (!iti.getTaskInstanceId().equals(task.getTaskInstanceId())) {
	            ITaskDefinition itd = iti.getTaskDefinition();
	            if (!blockingDefs.containsKey(itd.getId())) {
	                blockingDefs.put(itd.getId(), itd);
	            }
            }
        }
        return checkDefInList(blockingDefs, task.getTaskDefinition());
    }

    /**
     * returns true if the specified task definition can be blocked from
     * execution by any of the supplied task definition classes.
     * 
     * It does this by traversing the routings BACKWARDS from the supplied task
     * definition.
     * 
     * @param blockingDefs
     * @param taskDef
     * @return
     */
    private boolean checkDefInList(Map blockingDefs, ITaskDefinition taskDef) {
        Map checkList = new HashMap();
        Map visitedList = new HashMap();
        checkList.put(taskDef.getId(), taskDef);
        while (!checkList.isEmpty()) {
            ITaskDefinition checkDef = (ITaskDefinition) (checkList.values().toArray()[0]);
            // get inbound routings
            Set routingList = checkDef.getRoutingIn();
            for (Iterator it = routingList.iterator(); it.hasNext();) {
                IRoutingDefinition checkRouting = (IRoutingDefinition) it.next();
                ITaskDefinition srcTask = checkRouting.getOriginatingTaskDefinition();
                if (blockingDefs.containsKey(srcTask.getId())) {
                    if (log.isInfoEnabled()) {
                    	log.info("Task " + taskDef + " is being blocked by "  + srcTask);
                    }
                	return true;
                }
                if (!checkList.containsKey(srcTask.getId())) {
                    if (!visitedList.containsKey(srcTask.getId())) {
                        checkList.put(srcTask.getId(), srcTask);
                    }
                }
            }
            visitedList.put(checkDef.getId(), checkDef);
            checkList.remove(checkDef.getId());
        }
        return false;
    }
}