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

package uk.co.gidley.zebra.inmemory.services;

import uk.co.gidley.zebra.service.om.definitions.*;
import uk.co.gidley.zebra.service.om.definitions.Process;
import uk.co.gidley.zebra.service.services.ProcessDefinitionFactory;

import java.util.ArrayList;
import java.util.List;

/**
 * Created by IntelliJ IDEA. User: ben Date: Apr 15, 2010 Time: 7:04:51 PM
 */
public class InMemoryProcessDefinitionFactory implements ProcessDefinitionFactory {

    InMemoryDatastore inMemoryDatastore;

    public InMemoryProcessDefinitionFactory(InMemoryDatastore inMemoryDatastore) {
        this.inMemoryDatastore = inMemoryDatastore;


    }

    public TaskDefinition getTaskDefinition(Long id) {

        for (Process process : inMemoryDatastore.getProcessVersions()) {
            for (ProcessDefinition processDefinition : process.getProcessVersions()) {
                for (TaskDefinition taskDefinition : processDefinition.getTaskDefinitions()) {
                    if (taskDefinition.getId().equals(id)) {
                        return taskDefinition;
                    }
                }
            }
        }
        return null;
    }

    /**
     * TODO review if this function is useful - it is getting all versions of a taskdef but there is no obvious way to tell which one the caller would want
     *
     * @param processName
     * @param taskName
     * @return
     */
    public List<Long> getTaskDefinitionIds(String processName, String taskName) {
        for (uk.co.gidley.zebra.service.om.definitions.Process process : inMemoryDatastore.getProcessVersions()) {
            if (process.getName().equals(processName)) {
                List<Long> taskDefinitionIds = new ArrayList<Long>();
                for (ProcessDefinition processDefinition : process.getProcessVersions()) {
                    for (TaskDefinition taskDefinition : processDefinition.getTaskDefinitions()) {
                        if (taskDefinition.getName().equals(taskName)) {
                            taskDefinitionIds.add(taskDefinition.getId());
                        }
                    }
                }
                return taskDefinitionIds;
            }
        }
        return null;
    }

    public ProcessDefinition getProcessDefinitionById(Long id) {
        for (Process process : inMemoryDatastore.getProcessVersions()) {
            for (ProcessDefinition processDefinition : process.getProcessVersions()) {
                if (processDefinition.getId().equals(id)) {
                    return processDefinition;
                }
            }
        }
        return null;
    }

    public ProcessDefinition getProcessDefinitionByName(String name) {
        for (Process process : inMemoryDatastore.getProcessVersions()) {
            if (process.getName().equals(name)){
                return process.getLatestProcessVersion();
            }
        }
        return null;
    }
}
