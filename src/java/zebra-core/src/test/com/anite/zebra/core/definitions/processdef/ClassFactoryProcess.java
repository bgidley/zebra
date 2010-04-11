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

package com.anite.zebra.core.definitions.processdef;

import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.taskdefs.AutoRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.processconstruct.MockProcessConstruct;
import com.anite.zebra.core.processdestruct.MockProcessDestruct;
import com.anite.zebra.core.routingcondition.MockRoutingCondition;
import com.anite.zebra.core.taskaction.MockTaskAction;
import com.anite.zebra.core.taskconstruct.MockTaskConstruct;
import com.anite.zebra.core.taskdestruct.MockTaskDestruct;

/**
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class ClassFactoryProcess extends MockProcessDef {

	public MockTaskDef testTask;
	public MockRouting testRouting;
	/**
	 * @param name
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public ClassFactoryProcess(String name) {
		super(name);
		setup();
	}
	private void setup() {
		
		this.setClassConstruct(MockProcessConstruct.class.getName());
		this.setClassDestruct(MockProcessDestruct.class.getName());
		
		testTask = new AutoRunTaskDef(this,"TestTask");
		testTask.setClassConstruct(MockTaskConstruct.class.getName());
		testTask.setClassName(MockTaskAction.class.getName());
		testTask.setClassDestruct(MockTaskDestruct.class.getName());
		
		MockTaskDef td2 = new AutoRunTaskDef(this,"End");
		testRouting = testTask.addRoutingOut(td2);
		testRouting.setConditionClass(MockRoutingCondition.class.getName());
		
		this.setFirstTask(testTask);
	}

}
