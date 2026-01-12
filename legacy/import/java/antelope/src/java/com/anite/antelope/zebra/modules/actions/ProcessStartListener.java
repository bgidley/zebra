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
package com.anite.antelope.zebra.modules.actions;

import org.apache.turbine.util.RunData;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Listeners that are called by StartProcess action on process 
 * start.
 * 
 * For this to be called you MUST subclass startProcess. By default
 * no listeners are run.
 * 
 * The subclass will register the listeners
 * @author Ben Gidley
 */
public interface ProcessStartListener {
	/**
	 * Listen to a process starting
	 * If you modify it you MUST save it.
	 * @param processInstance
	 * @param data
	 */
	public void processStarting(AntelopeProcessInstance processInstance, RunData data, FormTool form) throws Exception;
}
