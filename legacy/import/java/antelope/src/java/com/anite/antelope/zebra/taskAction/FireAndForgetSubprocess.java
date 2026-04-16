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
package com.anite.antelope.zebra.taskAction;

import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;


/**
 * Creates a subprocess the immediately complete this task without further ado
 * 
 * Obviously (to me) no output paramters are returned.
 * 
 * This works by starting the subprocess as normal and then null ing the parent task instance.
 * This parent task is then set to STATE_AWAITINGCOMPLETE which forces the engine to not wait.
 * 
 * @author Ben.Gidley
 */
public class FireAndForgetSubprocess extends SubProcess {

    private final static Log log = LogFactory
            .getLog(FireAndForgetSubprocess.class);
    
    public void runTask(ITaskInstance taskInstance) throws RunTaskException {
        String processName = null;

        try {
            AntelopeTaskInstance antelopeTaskInstance = (AntelopeTaskInstance) taskInstance;
            processName = ((AntelopeTaskDefinition) taskInstance
                    .getTaskDefinition()).getSubProcessName();

            AntelopeProcessInstance subProcessInstance = ZebraHelper
                    .getInstance().createProcessPaused(processName);

            Session s = PersistenceLocator.getInstance().getCurrentSession();
            Transaction t = s.beginTransaction();

            subProcessInstance.setParentTaskInstance(antelopeTaskInstance);
            subProcessInstance
                    .setParentProcessInstance((AntelopeProcessInstance) antelopeTaskInstance
                            .getProcessInstance());
            
            // Map related class needed for security passing
            subProcessInstance.setRelatedClass(antelopeTaskInstance.getAntelopeProcessInstance().getRelatedClass());
            subProcessInstance.setRelatedKey(antelopeTaskInstance.getAntelopeProcessInstance().getRelatedKey());
            
            // map any inputs into the process
            mapTaskInputs((AntelopeProcessInstance) antelopeTaskInstance
                    .getProcessInstance(), subProcessInstance);
            
            // Now NULL parent taskinstace 
            subProcessInstance.setParentTaskInstance(null);
            
            s.saveOrUpdate(subProcessInstance);
            taskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
            s.saveOrUpdate(taskInstance);
            t.commit();
            
            // kick off the process
            ZebraHelper.getInstance().getEngine().startProcess(
                    subProcessInstance);            
        } catch (Exception e) {
            String emsg = "runTask failed to create Process " + processName;
            log.error(emsg, e);
            throw new RunTaskException(emsg, e);
        }

    }
}
