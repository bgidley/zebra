/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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

package com.anite.zebra.core.state.api;

import java.util.Set;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;

/**
 * @author Matthew.Norris
 */
public interface IProcessInstance extends IStateObject {
    public static final long STATE_RUNNING = 1;

    public static final long STATE_INITIALISING = 2;

    public static final long STATE_COMPLETING = 3;

    public static final long STATE_COMPLETE = 5;

    public static final long STATE_CREATED = 6;

    /**
     * returns the process definition this process instance is running
     * 
     * @return
     */
    public IProcessDefinition getProcessDef()
            throws DefinitionNotFoundException;

    public Long getProcessInstanceId();

    /**
     * returns the state of the process instance
     * 
     * @return
     */
    public long getState();

    public void setState(long state);

    /**
     * return ALL TaskInstances associated with this ProcessInstance. Should be
     * keyed by the TaskInstance ID.
     * 
     * @return
     */
    public Set getTaskInstances();

}