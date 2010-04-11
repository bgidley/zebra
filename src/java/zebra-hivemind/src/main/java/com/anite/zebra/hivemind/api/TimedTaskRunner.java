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
package com.anite.zebra.hivemind.api;

import java.util.Date;

import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.om.timedtask.Time;
import com.anite.zebra.hivemind.om.timedtask.TimedTask;

/**
 * Interface to queuing and running timed tasks.
 * @author Mike Jones
 *
 */
public interface TimedTaskRunner {

    /**
     * Run all the {@link TimedTask}'s for the {@link Time} 
     * @param time
     */
    public void runTasksForTime(Time time);

    /**
     * For the zebra task instance create a new timed task for to run at a specific time (this )
     * @param zti
     * @param time
     */
    public void scheduleTimedTask(ZebraTaskInstance zti, int hours, int mins, Date taskDate);

}
