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

package com.anite.antelope.modules.tasks;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Ben.Gidley
 */
public abstract class AbstractTaskAction implements ITaskAction {

    private final static Log log = LogFactory.getLog(AbstractTaskAction.class);
    
    /**
     * Sets the task into the correct state to proceed
     */
    public void runTask(ITaskInstance taskInstance) throws RunTaskException {

        runTask((AntelopeTaskInstance) taskInstance,
                (AntelopeProcessInstance) taskInstance.getProcessInstance());
        taskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
        try {
            ITransaction t = ZebraHelper.getInstance().getStateFactory().beginTransaction();
            ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance);
            ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance.getProcessInstance());
            t.commit();
        } catch (StateFailureException e) {
            log.error("Failed to save task on TaskAction",e);
            throw new RunTaskException(e);
        } catch (ComponentException e) {
            log.error("Failed to save task on TaskAction",e);
            throw new RunTaskException(e);
        }

    }

    public abstract void runTask(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance) throws RunTaskException;

}