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
package com.anite.zebra.hivemind.impl;

import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.List;

import org.apache.commons.logging.Log;
import org.apache.fulcrum.hivemind.RegistryManager;

import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.api.TimedTaskRunner;
import com.anite.zebra.hivemind.manager.FiredTimedTaskManager;
import com.anite.zebra.hivemind.manager.TimeManager;
import com.anite.zebra.hivemind.manager.TimedTaskManager;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.om.timedtask.FiredTimedTask;
import com.anite.zebra.hivemind.om.timedtask.Time;
import com.anite.zebra.hivemind.om.timedtask.TimedTask;

/**
 * Runs the tasks.
 * 
 * The manages all interactions with the OM Managers and Quartz.
 * 
 * Quartz is injected into the service
 * 
 * @author Mike Jones
 * @author Ben GIdley
 * 
 */
public class TimedTaskRunnerImpl implements TimedTaskRunner {

	static public final String MINUTE = "minute";

	static public final String HOUR = "hour";

	private TimedTaskManager timedTaskManager;

	private FiredTimedTaskManager firedTimedTaskManager;

	private TimeManager timeManager;

	private Log log;

	private Zebra zebra;

	public void setZebra(Zebra zebra) {
		this.zebra = zebra;
	}

	/*
	 * method for injection
	 */
	public void setFiredTimedTaskManager(
			FiredTimedTaskManager firedTimedTaskManager) {
		this.firedTimedTaskManager = firedTimedTaskManager;
	}

	/*
	 * Method for injection
	 */
	public void setLog(Log log) {
		this.log = log;
	}

	/*
	 * Method for injection
	 */
	public void setTimedTaskManager(TimedTaskManager timedTaskManager) {
		this.timedTaskManager = timedTaskManager;
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see com.anite.zebra.hivemind.api.TimedTaskRunner#runTasksForTime(com.anite.zebra.hivemind.om.timedtask.Time)
	 */
	public void runTasksForTime(Time time) {
		log.info("Beginning the " + time.getJobName() + " task run");

		List<TimedTask> timedTasks = timedTaskManager.getTasksForTime(time);

		log.info(time.getJobName() + " run: " + timedTasks.size()
				+ " tasks found");
		// for (TimedTask timedTask : timedTasks) {
		for (int i = 0; i < timedTasks.size(); i++) {
			TimedTask timedTask = timedTasks.get(i);
			if (isTaskDueToday(timedTask)) {
				log.info(time.getJobName() + " run: running task " + i);
				runTask(timedTask);
			}
		}
		log.info("Completed the " + time.getJobName() + " task run");
	}

	//checks to see if the task is due to be run today
	private boolean isTaskDueToday(TimedTask timedTask) {
		boolean taskOK = false;
		Calendar calendar = Calendar.getInstance();
		GregorianCalendar now = new GregorianCalendar();

		now.set(calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH),
				calendar.get(Calendar.DAY_OF_MONTH), 23, 59, 59);
		Date lastThingToday = new Date(now.getTimeInMillis());
		
	
		
		if (timedTask.getRunTaskDate() == null
				|| timedTask.getRunTaskDate().equals(lastThingToday)
				|| timedTask.getRunTaskDate().before(lastThingToday)) {

			taskOK = true;
		}
		return taskOK;

	}

	public void scheduleTimedTask(ZebraTaskInstance zti, int hours, int mins,
			Date taskDate) {

		TimedTask timedTask = new TimedTask();
		Time time = getTimeManager().createOrFetchTime(hours, mins);
		timedTask.setZebraTaskInstanceId(zti.getTaskInstanceId());
		timedTask.setTime(time);
		timedTask.setRunTaskDate(taskDate);
		getTimedTaskManager().saveOrUpdate(timedTask);
	}

	/**
	 * Runt the timed task by retrieving the associated zebra task instance and
	 * transtioningit it
	 * 
	 * @param timedTask
	 */
	protected void runTask(TimedTask timedTask) {
		log
				.debug("Running Task Instance:"
						+ timedTask.getZebraTaskInstanceId());

		FiredTimedTask firedTimedTask = new FiredTimedTask(timedTask);
		try {
			ZebraTaskInstance zti = zebra.getStateFactory().loadTaskInstance(
					timedTask.getZebraTaskInstanceId());

			zti.setOutcome("Done");
			zti.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);

			firedTimedTask.setZebraTaskInstanceId(zti.getTaskInstanceId());
			firedTimedTask.setStartTime(new Date());
			zebra.transitionTask(zti);
			firedTimedTask.setFailed(false);
			firedTimedTask.setEndTime(new Date());
		} catch (TransitionException e) {
			log.error(e);
			firedTimedTask.setExceptionText("Failed to transition task: "
					+ e.getMessage());
			firedTimedTask.setFailed(true);
		} catch (Throwable e) {
			log.error(e);
			firedTimedTask.setExceptionText("Throwable: " + e.getMessage());
			firedTimedTask.setFailed(true);
		} finally {
			firedTimedTaskManager.saveOrUpdate(firedTimedTask);
			timedTaskManager.delete(timedTask);
			RegistryManager.getInstance().getRegistry().cleanupThread();
		}

	}

	public TimeManager getTimeManager() {
		return timeManager;
	}

	public void setTimeManager(TimeManager timeManager) {
		this.timeManager = timeManager;
	}

	public FiredTimedTaskManager getFiredTimedTaskManager() {
		return firedTimedTaskManager;
	}

	public TimedTaskManager getTimedTaskManager() {
		return timedTaskManager;
	}

	public void scheduleTimedTask(ZebraTaskInstance zti, int hours, int mins,
			java.sql.Date date) {
		// TODO Auto-generated method stub

	}

}
