/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.taskAction;

import org.apache.fulcrum.hivemind.RegistryManager;

import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;

/**
 * A TaskAction that delegates execution down to a hivemind service with all
 * the goodness that can include.
 * 
 * The Service must implement the ITaskAction interface
 * 
 * @author ben.gidley
 *
 */
public class HivemindServiceTaskAction implements ITaskAction {
    
    public void runTask(ITaskInstance taskInstance) throws RunTaskException {
        try {
            String serviceId = ((ZebraTaskDefinition) taskInstance.getTaskDefinition()).getGeneralProperties()
                    .getString("ServiceId");

            ITaskAction action = (ITaskAction) RegistryManager.getInstance().getRegistry().getService(serviceId,
                    ITaskAction.class);
            action.runTask(taskInstance);

            
        } catch (DefinitionNotFoundException e) {
            throw new RunTaskException(
                    "I am running inside a task that does not exist. This is too hard to contemplate", e);
        }

    }

}
