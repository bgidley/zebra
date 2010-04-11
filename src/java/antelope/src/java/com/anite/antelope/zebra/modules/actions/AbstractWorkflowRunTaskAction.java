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

import net.sf.hibernate.HibernateException;

import org.apache.commons.lang.exception.NestableException;
import org.apache.turbine.modules.actions.VelocitySecureAction;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.helper.ZebraSessionData;
import com.anite.antelope.zebra.modules.tools.TaskInstanceTool;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Provides the functionality to run a task
 * 
 * @author Ben.Gidley
 */
public abstract class AbstractWorkflowRunTaskAction extends VelocitySecureAction {

    /**
     * Work out which screen to show next
     * 
     * @param data
     * @param form
     * @param processInstance
     * @throws HibernateException
     * @throws NestableException
     */
    protected void determineNextScreen(RunData data, FormTool form, AntelopeProcessInstance processInstance, Context context)
            throws HibernateException, NestableException {
        data.getSession().removeAttribute(ZebraSessionData.SESSION_KEY);
        AntelopeTaskInstance nextTaskInstance = processInstance.determineNextScreenTask();

        if (nextTaskInstance != null) {
            setNextTask(data, form, context, nextTaskInstance);
        } else {
            this.setTemplate(data, ZebraHelper.getInstance().getTaskListScreenName());
            form.reinitialiseForScreenEndpoint();
        }
    }

    /**
     * @param data
     * @param form
     * @param context
     * @param nextTaskInstance
     */
    protected void setNextTask(RunData data, FormTool form, Context context, AntelopeTaskInstance nextTaskInstance) {

        this.setTemplate(data, ((AntelopeTaskDefinition) nextTaskInstance.getTaskDefinition()).getScreenName());

        ZebraSessionData zebraSessonData = new ZebraSessionData();
        zebraSessonData.setTaskInstanceId(nextTaskInstance.getTaskInstanceId());

        data.getSession().setAttribute(ZebraSessionData.SESSION_KEY, zebraSessonData);
        TaskInstanceTool taskTool = (TaskInstanceTool) context.get(TaskInstanceTool.DEFAULT_TOOL_NAME);
        taskTool.initialise();
        form.reinitialiseForScreenEndpoint();
    }
}