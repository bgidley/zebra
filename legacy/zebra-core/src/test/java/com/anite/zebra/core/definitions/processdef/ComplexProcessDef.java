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
import com.anite.zebra.core.definitions.taskdefs.JoinTaskDef;
import com.anite.zebra.core.definitions.taskdefs.ManualRunTaskDef;
import com.anite.zebra.core.definitions.taskdefs.MockTaskDef;
import com.anite.zebra.core.definitions.taskdefs.SplitTaskDef;
import com.anite.zebra.core.routingcondition.MockRoutingCondition;

/**
 * @author Matthew Norris
 * Created on 19-Aug-2005
 *
 */
public class ComplexProcessDef extends MockProcessDef {
	
	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 */
	public static final String GOTO = "Goto ";
	public MockTaskDef tdStart;
	public MockTaskDef tdJoin;
	public MockTaskDef tdParallel_1;
	public MockTaskDef tdParallel_2;
	public MockTaskDef tdAlternateEnding;
	public MockTaskDef tdSplit;
	public MockTaskDef tdEnd;

	public ComplexProcessDef(String name) {
		super(name);
		setup();
	}
	
	private void setup() {
		tdStart = new ManualRunTaskDef(this,"Start");
		this.setFirstTask(tdStart);
		
		tdSplit = new SplitTaskDef(this,"Split");
		tdStart.addRoutingOut(tdSplit);
		
		
		tdParallel_1 = new ManualRunTaskDef (this,"Parallel-1");
		tdSplit.addRoutingOut(tdParallel_1);
		
		tdParallel_2 = new ManualRunTaskDef (this,"Parallel-2");
		tdSplit.addRoutingOut(tdParallel_2);		
		
		tdJoin = new JoinTaskDef(this,"Join");
		tdParallel_1.addRoutingOut(tdJoin);

		MockRouting mr1 = tdParallel_2.addRoutingOut(tdJoin);
		mr1.setName(GOTO + tdJoin.getName());
		mr1.setConditionClass(MockRoutingCondition.class.getName());
		
		MockRouting mr2 = tdParallel_2.addRoutingOut(tdSplit);
		mr2.setName(GOTO + tdSplit.getName());
		mr2.setConditionClass(MockRoutingCondition.class.getName());
		
		tdAlternateEnding = new ManualRunTaskDef(this,"Alternate Ending");
		MockRouting mr3 = tdParallel_2.addRoutingOut(tdAlternateEnding);
		mr3.setName(GOTO + tdAlternateEnding.getName());
		mr3.setConditionClass(MockRoutingCondition.class.getName());
	
		tdEnd = new ManualRunTaskDef(this,"End");
		tdJoin.addRoutingOut(tdEnd);
		
	}

}
