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

import java.util.Iterator;

import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * Performs a subflow step. 
 * The subflow is initialised. 
 *  
 * This task must leave it's Task state alone; the task State will be updated by ProcessDestruct
 * class when the process that has been created has completed 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
public class SubProcess implements ITaskAction {
    private static Log log = LogFactory.getLog(SubProcess.class);

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
            
            s.saveOrUpdate(subProcessInstance);
            t.commit();

            // map any inputs into the process
            mapTaskInputs((AntelopeProcessInstance) antelopeTaskInstance
                    .getProcessInstance(), subProcessInstance);

            // kick off the process
            ZebraHelper.getInstance().getEngine().startProcess(
                    subProcessInstance);

        } catch (Exception e) {
            String emsg = "runTask failed to create Process " + processName;
            log.error(emsg, e);
            throw new RunTaskException(emsg, e);
        }

    }

    /**
     * maps the inputs of the specified process to the parameters set against
     * this task
     */
    protected void mapTaskInputs(AntelopeProcessInstance parentProcess,
            AntelopeProcessInstance subProcess) throws RunTaskException {

        log.debug("Called mapTaskInputs");

        try {
            AntelopeProcessDefinition subFlowProcessDefinition = (AntelopeProcessDefinition) subProcess
                    .getProcessDef();
            AntelopeTaskDefinition parentTaskDefinition = (AntelopeTaskDefinition) subProcess
                    .getParentTaskInstance().getTaskDefinition();

            Iterator inputs = subFlowProcessDefinition.getInputs().keys();
            while (inputs.hasNext()) {
                String key = (String) inputs.next();

                AntelopePropertySetEntry value;
                if (parentProcess.getPropertySet().containsKey(
                        key)) {
                    value = (AntelopePropertySetEntry) parentProcess.getPropertySet().get(
                            key);
                } else if (parentTaskDefinition.getInputs().containsKey(key)) {
                	AntelopePropertySetEntry element = new AntelopePropertySetEntry();
                    element.setValue((String) parentTaskDefinition.getInputs()
                            .get(key));
                    value = element;
                } else {
                	AntelopePropertySetEntry element = new AntelopePropertySetEntry();
                    element.setValue((String) subFlowProcessDefinition
                            .getInputs().get(key));
                    value = element;
                }
                //value = (AntelopePropertySetEntry) PersistenceLocator.getInstance().getCurrentSession().saveOrUpdateCopy(value);
                // Take a COPY
                AntelopePropertySetEntry copyValue = new AntelopePropertySetEntry();
                copyValue.setValue(value.getValue());
                copyValue.setObject(value.getObject());
                subProcess.getPropertySet().put(key, copyValue);
            }
        } catch (Exception e) {
            String emsg = "Error occurred when mapping property inputs for TaskInstance:"
                    + subProcess.getParentTaskInstance().getTaskInstanceId();
            log.error(emsg, e);
            throw new RunTaskException(emsg, e);
        }
    }

}