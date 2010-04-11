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
package com.anite.zebra.core.definitions.taskdefs;
import java.util.HashSet;
import java.util.Set;

import com.anite.zebra.core.definitions.MockProcessDef;
import com.anite.zebra.core.definitions.MockRouting;
import com.anite.zebra.core.definitions.MockTaskDefinitions;
import com.anite.zebra.core.definitions.api.ITaskDefinition;

/**
 * @author Matthew Norris
 * Created on 19-Aug-2005
 */
public class MockTaskDef implements ITaskDefinition {

	private static long idCounter = 1;
	private Long id = null;
	private boolean auto = false;
	private String className = null;
	private boolean synchronised = false;
	private Set routingOut = new HashSet();
	private Set routingIn = new HashSet();
	private String classConstruct = null;
	private String classDestruct = null;
	private String name = null;
	private MockProcessDef processDef = null;
	
	public MockTaskDef(MockProcessDef pd, String taskName) {
		this.processDef = pd;
		MockTaskDefinitions mtd = (MockTaskDefinitions) pd.getTaskDefs();
		this.id = new Long(idCounter++);
		this.name = taskName;
		mtd.add(this);
	}
	
	public Long getId() {
		return id;
	}

	public boolean isAuto() {
		return auto;
	}

	public String getClassName() {
		return className;
	}

	public boolean isSynchronised() {
		return synchronised;
	}

	public Set getRoutingOut() {
		return routingOut;
	}

	public Set getRoutingIn() {
		return routingIn;
	}

	public String getClassConstruct() {
		return classConstruct;
	}

	public String getClassDestruct() {
		return classDestruct;
	}

	public void setAuto(boolean auto) {
		this.auto = auto;
	}

	public void setClassConstruct(String classConstruct) {
		this.classConstruct = classConstruct;
	}

	public void setClassDestruct(String classDestruct) {
		this.classDestruct = classDestruct;
	}

	public void setClassName(String className) {
		this.className = className;
	}

	public void setSynchronised(boolean synchronised) {
		this.synchronised = synchronised;
	}

	public String getName() {
		return this.name;
	}
	public MockProcessDef getProcessDef(){
		return this.processDef;
	}
	
	public MockRouting addRoutingOut(MockTaskDef destination) {
		MockRouting mr = new MockRouting(this,destination);
		return mr;
	}

	public String toString() {
		return "MOCK-DEF-ID "+ this.id + "[" + this.name + "]";
	}
	
	
}
