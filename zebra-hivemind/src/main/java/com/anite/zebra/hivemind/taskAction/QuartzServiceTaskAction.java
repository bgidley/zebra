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

import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.hivemind.api.TimedTaskRunner;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.om.state.ZebraPropertySetEntry;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * Kick off the quartz job once every 24 hours
 * 
 * By default we will kick off at 19:00
 * 
 * This can be changed in the designer.
 * 
 * This is a hivemind service so you can use dependency injection.
 * 
 * @TODO Change the designer template to allow setting on hour/minute
 * @TODO test me
 * 
 * @author ben.gidley
 * 
 */
public class QuartzServiceTaskAction extends ZebraTaskAction {

	public static final Log log = LogFactory
			.getLog(QuartzServiceTaskAction.class);

	private TimedTaskRunner timedTaskRunner;

	/**
	 * When this task is run, it waits until the scheduled time and then runs
	 * the QuartzJob. This job is given the taskInstanceId and is responsible
	 * for tranistioning the task when the trigger is fired.
	 */
	public void runTask(ZebraTaskInstance taskInstance) throws RunTaskException {

		Date taskDate = null;
		try {
			int hour = 19;
			int minute = 0;

			ZebraTaskDefinition zebraTaskDefinition = (ZebraTaskDefinition) taskInstance
					.getTaskDefinition();

			// gets the task date set in the property set
			ZebraProcessInstance pi = taskInstance.getZebraProcessInstance();
			if (pi.getPropertySet().containsKey("TaskDate")) {
				ZebraPropertySetEntry pse = pi.getPropertySet()
						.get("TaskDate");

				SimpleDateFormat sdf = new SimpleDateFormat("dd/MM/yyyy");

				
				try {
					taskDate = sdf.parse(pse.getValue());
				} catch (ParseException e) {
					log.error("unable to parse taskDate", e);
					e.printStackTrace();
				}

			}

			if (zebraTaskDefinition.getGeneralProperties().containsKey("hour")) {
				hour = zebraTaskDefinition.getGeneralProperties().getInteger(
						"hour");
			}
			if (zebraTaskDefinition.getGeneralProperties()
					.containsKey("minute")) {
				minute = zebraTaskDefinition.getGeneralProperties().getInteger(
						"minute");
			}

			timedTaskRunner.scheduleTimedTask(taskInstance, hour, minute,
					taskDate);
		} catch (DefinitionNotFoundException e) {
			throw new RunTaskException(e);
		}
	}

	public TimedTaskRunner getTimedTaskRunner() {
		return timedTaskRunner;
	}

	public void setTimedTaskRunner(TimedTaskRunner timedTaskRunner) {
		this.timedTaskRunner = timedTaskRunner;
	}
}
