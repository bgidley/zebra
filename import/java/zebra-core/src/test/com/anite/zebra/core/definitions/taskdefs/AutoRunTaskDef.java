package com.anite.zebra.core.definitions.taskdefs;
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
import com.anite.zebra.core.definitions.MockProcessDef;


/**
 * @author Eric Pugh
 *
 * TODO To change the template for this generated type comment go to
 * Window - Preferences - Java - Code Style - Code Templates
 */
public class AutoRunTaskDef extends MockTaskDef {

	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @param pd
	 */
	public AutoRunTaskDef(MockProcessDef pd, String taskName) {
		super(pd,taskName);
		this.setAuto(true);
	}
	
}
