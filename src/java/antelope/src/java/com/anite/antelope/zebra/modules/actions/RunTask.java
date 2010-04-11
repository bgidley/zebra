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

package com.anite.antelope.zebra.modules.actions;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * This is the standard action to run a task
 * @author Ben.Gidley
 */
public class RunTask extends AbstractWorkflowRunTaskAction {

    private static final String TASK_INSTANCE_ID = "taskinstanceid";

    /**
     * Assumes screen has been set to source page
     * Run a task if it has a screen show it
     * If not attempt transition and go back to task list
     * @TODO handle task ownership
     */
    public void doPerform(RunData data, Context context) throws Exception {
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            Field taskInstance = (Field) form.getFields().get(TASK_INSTANCE_ID);

            AntelopeTaskInstance antelopeTaskInstance = ZebraHelper
                    .getInstance().getTaskInstance(
                            new Long(taskInstance.getValue()));

            if (antelopeTaskInstance == null) {
                taskInstance.addMessage("Invalid task instance");
                return;
            }

            ZebraSessionData zebraSessionData = new ZebraSessionData();
            zebraSessionData.setTaskInstanceId(antelopeTaskInstance
                    .getTaskInstanceId());

            String nextScreen = ((AntelopeTaskDefinition) antelopeTaskInstance
                    .getTaskDefinition()).getScreenName();

            if (nextScreen != null) {
                this.setNextTask(data, form, context, antelopeTaskInstance);
            } else {
                AntelopeProcessInstance processInstance = (AntelopeProcessInstance) antelopeTaskInstance
                        .getProcessInstance();
                // Try and transistion the task either move to next task or to the task list
                ZebraHelper.getInstance().getEngine().transitionTask(
                        antelopeTaskInstance);
                determineNextScreen(data, form, processInstance, context);
            }
        }
    }

    /**
     * Just here because it has to be
     */
    protected boolean isAuthorized(RunData data) throws Exception {

        return true;
    }

}