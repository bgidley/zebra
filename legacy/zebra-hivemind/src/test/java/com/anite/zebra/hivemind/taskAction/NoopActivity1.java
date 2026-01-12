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

import com.anite.zebra.core.exceptions.RunTaskException;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

public class NoopActivity1 extends ZebraTaskAction{
    
    public static int executionCount = 0;

    @Override
    public void runTask(ZebraTaskInstance zebraTaskInstance) throws RunTaskException {
       zebraTaskInstance.setState(ITaskInstance.STATE_AWAITINGCOMPLETE);
       executionCount++;
    }

}
