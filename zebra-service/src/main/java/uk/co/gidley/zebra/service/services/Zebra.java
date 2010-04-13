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

package uk.co.gidley.zebra.service.services;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.DestructException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.ITransaction;
import uk.co.gidley.zebra.service.internal.services.ProcessDefinitionFactory;

import java.util.Iterator;
import java.util.List;
import java.util.Set;

/**
 * This is the main facade class for Zebra
 * <p/>
 * This holds references to the key Zebra interfaces and helper functions for all commonly used operations
 *
 * @author ben.gidley
 */
public class Zebra {

	private ProcessDefinitionFactory definitionFactory;

	private ZebraStateFactory stateFactory;

	private IEngine engine;

	private ZebraSecurity zebraSecurity;


	public Zebra(ProcessDefinitionFactory processDefinitionFactory) {
		this.definitionFactory = processDefinitionFactory;

	}

	public ZebraProcessDefinition getProcessDefinition(String processName) {
		return this.definitionFactory.getProcessDefinitionByName(processName);
	}

	/**
	 * Creates a process in a paused state by name
	 *
	 * @param processName
	 * @return
	 * @throws com.anite.zebra.core.exceptions.CreateProcessException
	 *
	 */
	public ZebraProcessInstance createProcessPaused(String processName) throws CreateProcessException {
		return createProcessPaused(this.getProcessDefinition(processName));

	}

	/**
	 * Creates a process in a paused state by process definition
	 *
	 * @param process
	 * @return
	 * @throws CreateProcessException
	 */
	public ZebraProcessInstance createProcessPaused(ZebraProcessDefinition process) throws CreateProcessException {
		return (ZebraProcessInstance) engine.createProcess(process);

	}

	/**
	 * Gets the task list for the passed user
	 *
	 * @param user
	 * @return
	 */
	public List<ZebraTaskInstance> getTaskList(DynamicUser user) {

		return zebraSecurity.getTaskList(user);

	}

	public List<ZebraTaskInstance> getOnlyOwnedTaskList(HibernateDynamicUser user) {

		return zebraSecurity.getOnlyOwnedTaskList(user);
	}

	public List<ZebraTaskInstance> getOnlyDelegatedTaskList(HibernateDynamicUser user) {

		return zebraSecurity.getOnlyDelegatedTaskList(user);
	}

	public void startProcess(ZebraProcessInstance processInstance) throws StartProcessException {
		engine.startProcess(processInstance);

	}

	public void transitionTask(ZebraTaskInstance taskInstance) throws TransitionException {
		engine.transitionTask(taskInstance);
	}

	/**
	 * Kill this process and all tasks within it. This does NOT kill the parent process but will kill child processes.
	 * If these is a parent it will be tiggered to move on by the process destruct step
	 * <p/>
	 * The application is expected to handle security over who can kill a process it is NOT enforced here
	 * <p/>
	 * If this is a child process the subflow step will be marked complete
	 * <p/>
	 * TODO consider moving into the StateFactory Interface
	 *
	 * @throws com.anite.zebra.core.factory.exceptions.StateFailureException
	 *
	 * @throws com.anite.zebra.core.exceptions.DestructException
	 *
	 */
	public void killProcess(ZebraProcessInstance processInstance,
			HibernateDynamicUser owner) throws StateFailureException,
			DestructException {

		List<ZebraProcessInstance> processesToKill = processInstance.getRunningChildProcesses();
		processesToKill.add(processInstance);

		ITransaction t = stateFactory.beginTransaction();

		for (Iterator iter = processesToKill.iterator(); iter.hasNext();) {
			ZebraProcessInstance process = (ZebraProcessInstance) iter.next();

			Set<ZebraTaskInstance> tasks = process.getTaskInstances();

			for (ZebraTaskInstance task : tasks) {
				task.setState(ZebraTaskInstance.KILLED);
				task.setTaskOwner(owner);
				stateFactory.saveObject(task);

				// This will create history automatically and will remove itself
				// from the set
				stateFactory.deleteObject(task);
				process.setState(ZebraTaskInstance.KILLED);
				stateFactory.saveObject(process);
			}

		}
		t.commit();

		// Only destroy this process if there is a parent to force a subflow
		// return
		// - no need to do the child tree - as they are all killed
		if (processInstance.getParentProcessInstance() != null) {
			ProcessDestruct destructor = new ProcessDestruct();
			destructor.processDestruct(processInstance);
		}
	}


}

