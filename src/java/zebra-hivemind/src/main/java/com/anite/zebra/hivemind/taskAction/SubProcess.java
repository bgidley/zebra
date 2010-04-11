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

package com.anite.zebra.hivemind.taskAction;

import java.util.Iterator;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.Session;
import org.hibernate.Transaction;

import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.impl.Zebra;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraPropertySetEntry;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.util.RegistryHelper;

/**
 * Performs a subflow step. The subflow is initialised.
 * 
 * This task must leave it's Task state alone; the task State will be updated by
 * ProcessDestruct class when the process that has been created has completed
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
public class SubProcess implements ITaskAction {
	private static Log log = LogFactory.getLog(SubProcess.class);

	public void runTask(ITaskInstance taskInstance) throws RunTaskException {
		String processName = null;

		Zebra zebra = RegistryHelper.getInstance().getZebra();

		try {
			ZebraTaskInstance antelopeTaskInstance = (ZebraTaskInstance) taskInstance;
			processName = ((ZebraTaskDefinition) taskInstance
					.getTaskDefinition()).getSubProcessName();

			ZebraProcessInstance subProcessInstance = zebra
					.createProcessPaused(processName);

			Session s = RegistryHelper.getInstance().getSession();
			Transaction t = s.beginTransaction();

			subProcessInstance.setParentTaskInstance(antelopeTaskInstance);
			subProcessInstance
					.setParentProcessInstance((ZebraProcessInstance) antelopeTaskInstance
							.getProcessInstance());

			// Map related class needed for security passing
			subProcessInstance.setRelatedClass(antelopeTaskInstance
					.getZebraProcessInstance().getRelatedClass());
			subProcessInstance.setRelatedKey(antelopeTaskInstance
					.getZebraProcessInstance().getRelatedKey());

			s.saveOrUpdate(subProcessInstance);
			t.commit();

			// map any inputs into the process
			mapTaskInputs((ZebraProcessInstance) antelopeTaskInstance
					.getProcessInstance(), subProcessInstance);

			// kick off the process
			zebra.startProcess(subProcessInstance);

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
	protected void mapTaskInputs(ZebraProcessInstance parentProcess,
			ZebraProcessInstance subProcess) throws RunTaskException {

		log.debug("Called mapTaskInputs");

		try {
			ZebraProcessDefinition subFlowProcessDefinition = (ZebraProcessDefinition) subProcess
					.getProcessDef();
			ZebraTaskDefinition parentTaskDefinition = (ZebraTaskDefinition) subProcess
					.getParentTaskInstance().getTaskDefinition();

			Iterator inputs = subFlowProcessDefinition.getInputs().keys();
			while (inputs.hasNext()) {
				String key = (String) inputs.next();

				ZebraPropertySetEntry value;
				if (parentProcess.getPropertySet().containsKey(key)) {
					value = parentProcess.getPropertySet().get(key);
					
				} else if (parentTaskDefinition.getInputs().containsKey(key)) {
					ZebraPropertySetEntry element = new ZebraPropertySetEntry();
					element.setValue((String) parentTaskDefinition.getInputs()
							.get(key));
					value = element;
					
				} else {
					ZebraPropertySetEntry element = new ZebraPropertySetEntry();
					element.setValue((String) subFlowProcessDefinition
							.getInputs().get(key));
					value = element;
				}

				// Take a COPY
				ZebraPropertySetEntry copyValue = new ZebraPropertySetEntry();
				copyValue.setValue(value.getValue());
				copyValue.setObject(value.getObject());
				copyValue.setProcessInstance(subProcess);
				copyValue.setKey(key);
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