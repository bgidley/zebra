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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.Session;
import org.hibernate.Transaction;

import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.impl.Zebra;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.util.RegistryHelper;

/**
 * Creates a subprocess the immediately complete this task without further ado
 * 
 * Obviously (to me) no output paramters are returned.
 * 
 * This works by starting the subprocess as normal and then null ing the parent
 * task instance. This parent task is then set to STATE_AWAITINGCOMPLETE which
 * forces the engine to not wait.
 * 
 * @author Ben.Gidley
 */
public class FireAndForgetSubprocess extends SubProcess {

	private final static Log log = LogFactory
			.getLog(FireAndForgetSubprocess.class);

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

			// map any inputs into the process
			mapTaskInputs((ZebraProcessInstance) antelopeTaskInstance
					.getProcessInstance(), subProcessInstance);

			// Now NULL parent taskinstace
			subProcessInstance.setParentTaskInstance(null);

			s.saveOrUpdate(subProcessInstance);
			taskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
			s.saveOrUpdate(taskInstance);
			t.commit();

			// kick off the process
			zebra.startProcess(subProcessInstance);
		} catch (Exception e) {
			String emsg = "runTask failed to create Process " + processName;
			log.error(emsg, e);
			throw new RunTaskException(emsg, e);
		}

	}
}
