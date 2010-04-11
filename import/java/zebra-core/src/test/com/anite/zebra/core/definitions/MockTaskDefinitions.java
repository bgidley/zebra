package com.anite.zebra.core.definitions;
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
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinitions;


public class MockTaskDefinitions implements ITaskDefinitions {

	private final IProcessDefinition def;
	private Map taskDefs = new HashMap();
	

	public MockTaskDefinitions(IProcessDefinition def) {
		this.def = def;
	}

	public IProcessDefinition getProcessDef() {
		return def;
	}

	public ITaskDefinition getTaskDef(Long id) {
		return (ITaskDefinition)taskDefs.get(id);
	}

	public void add(ITaskDefinition taskDef) {
		taskDefs.put(taskDef.getId(),taskDef);

	}
	public Iterator iterator(){
	    return taskDefs.values().iterator();
	}
	public long size() {
		return taskDefs.size();
	}
}