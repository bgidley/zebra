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

import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * A simple wrapper to avoid all task actions having to down cast the Task instance themselves
 * @author ben.gidley
 *
 */
public abstract class ZebraTaskAction implements ITaskAction {

    public final void runTask(ITaskInstance task) throws RunTaskException {
        try {
            this.runTask((ZebraTaskInstance) task);
        } catch (Throwable e) {
            // This should not be necessary - but as some badly written tasks have been
            // throwing RunTimeExceptions we have this.
            // Throwing a runtime exceptions is an extremely bad idea as it leaves locks on the process 
            // in the DB
            throw new RunTaskException(e);
        }
    }

    /**
     * Execute the task
     * @param zebraTaskInstance
     * @throws RunTaskException
     * @see ITaskAction
     */
    public abstract void runTask(ZebraTaskInstance zebraTaskInstance) throws RunTaskException;

}
