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

package com.anite.antelope.zebra.processLifecycle;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.zebra.core.api.IProcessConstruct;
import com.anite.zebra.core.exceptions.ConstructException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * Subprocess aware process constructor
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
public class ProcessConstruct implements IProcessConstruct {

    private static Log log = LogFactory.getLog(ProcessConstruct.class);

    public void processConstruct(IProcessInstance processInstance)
            throws ConstructException {
        if (log.isInfoEnabled()) {
            log.info("processConstruct called for InterfaceProcessInstance "
                    + processInstance.getProcessInstanceId());
        }
        try {
            AntelopeProcessInstance antelopeProcessInstance = (AntelopeProcessInstance) processInstance;
            processConstruct(antelopeProcessInstance);
        } catch (Exception e) {
            log.error(e);
            throw new ConstructException(e);
        }
    }

    /**
     * Construct a process with its default input and outputs
     * @param processInstance
     * @throws ConstructException
     */
    public void processConstruct(AntelopeProcessInstance processInstance)
            throws ConstructException {
        // Do nothing
    }

}