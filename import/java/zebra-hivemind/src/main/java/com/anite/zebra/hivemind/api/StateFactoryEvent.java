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

import java.util.EventObject;

import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

/**
 * Event fired when state factory creates a task instance
 * @author ben.gidley
 *
 */
public class StateFactoryEvent extends EventObject {

    /**
     * 
     */
    private static final long serialVersionUID = -8030993197997220325L;
    private ZebraTaskInstance zebraTaskInstance;
    
    public ZebraTaskInstance getZebraTaskInstance() {
        return zebraTaskInstance;
    }

    public StateFactoryEvent(Object source, ZebraTaskInstance zebraTaskInstance) {
        super(source);
        this.zebraTaskInstance = zebraTaskInstance;
    }

}
