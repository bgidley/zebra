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

package com.anite.antelope.modules.screens;

import java.util.Collections;
import java.util.List;

import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.comparators.tasklist.CaptionComparator;
import com.anite.antelope.comparators.tasklist.DateCreatedComparator;
import com.anite.antelope.comparators.tasklist.TaskListComparator;
import com.anite.antelope.zebra.helper.ZebraHelper;

/**
 * @author Ben.Gidley
 * @author Mike
 */
public class TaskList extends VelocityScreen {

    /**
     * Load the task list for the current user
     */
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {

        List tasks = ZebraHelper.getInstance().getTaskList();

        String column = data.getParameters().get("column");
        String direction = data.getParameters().get("direction");

        // set the defaults if nothing chose (eg entering page for first time)
        if (column == null) {
            column = "task";
            direction = "down";
        }

        //set the comparator to sort the list
        TaskListComparator c = null;
        if (column.equals("task")) {
            c = new CaptionComparator();
        } else if (column.equals("created")) {
            c = new DateCreatedComparator();
        } else if (column.equals("owner")) {
            // TODO : when the owner has been set create a comparator for it to be sorted by
            c = new CaptionComparator();
        }

        if (c != null) {
            // set the direction
            if (direction.equals("down")) {
                c.setDirection(TaskListComparator.DESCENDING);
            } else {
                c.setDirection(TaskListComparator.ASCENDING);
            }
            Collections.sort(tasks, c);
        }
        context.put("tasks", tasks);
        context.put("column", column);
        context.put("direction", direction);
    }
}