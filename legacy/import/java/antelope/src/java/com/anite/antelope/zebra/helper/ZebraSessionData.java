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

package com.anite.antelope.zebra.helper;



import org.apache.commons.lang.exception.NestableException;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 * Class to hold current workflow information in the session 
 * @author Matthew Norris
 * @author Ben Gidley
 */
public class ZebraSessionData {
    
    public final static String SESSION_KEY = "com.anite.antelope.zebra.helper.ZebraSessionData";

    private Long taskInstanceId = null;

    public void clearAll() {
        taskInstanceId = null;
    }

    /**
     * clears all workflow-related stuff from the session
     */
    public void clearWorkflow() {
        this.taskInstanceId = null;
    }

    public void setTaskInstanceId(Long taskInstanceId) {
        this.taskInstanceId = taskInstanceId;
    }

    /**
     * @return Task Instance
     * @throws NestableException
     * @throws BaseCtmsException
     *             base ctms exception
     */
    public AntelopeTaskInstance getTaskInstance() throws NestableException {
        if (this.taskInstanceId == null) {
            return null;
        }
        return ZebraHelper.getInstance().getTaskInstance(this.taskInstanceId);
    }

    public AntelopeProcessInstance getProcessInstance() throws NestableException {
        if (this.taskInstanceId == null) {
            return null;
        }
        return (AntelopeProcessInstance) getTaskInstance().getProcessInstance();
    }

    public Long getTaskInstanceId() {
        return this.taskInstanceId;
    }
}