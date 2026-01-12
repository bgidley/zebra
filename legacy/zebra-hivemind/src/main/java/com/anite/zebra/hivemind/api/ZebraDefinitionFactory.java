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

import java.util.List;

import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;

public interface ZebraDefinitionFactory {
    public abstract ZebraTaskDefinition getTaskDefinition(Long id);

    public abstract List<Long> getTaskDefinitionIds(String processName, String taskName);

    public abstract ZebraProcessDefinition getProcessDefinitionById(Long id);

    public abstract ZebraProcessDefinition getProcessDefinitionByName(String name);

}
