/*
 * Original Code Copyright 2004, 2005 Anite - Central Government Division
 * http://www.anite.com/publicsector
 *
 * Modifications Copyright 2010 Ben Gidley
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */

package uk.co.gidley.zebra.service.om.definitions;

import com.anite.zebra.core.definitions.api.ITaskDefinition;

import java.util.Set;

/**
 * Created by IntelliJ IDEA. User: ben Date: Apr 13, 2010 Time: 8:19:04 AM
 */
public class TaskDefinition implements ITaskDefinition {

	private String name;

	private Long id;

	private boolean auto;

	private String className;

	private Set<RoutingDefinition> routingOut;

	private Set<RoutingDefinition> routingIn;

	private String classConstruct;

	private String classDestruct;

	private boolean synchronised;

	public boolean isSynchronised() {
		return synchronised;
	}

	public void setSynchronised(boolean synchronised) {
		this.synchronised = synchronised;
	}

	public Long getId() {
		return id;
	}

	public void setId(Long id) {
		this.id = id;
	}

	public boolean isAuto() {
		return auto;
	}

	public void setAuto(boolean auto) {
		this.auto = auto;
	}

	public String getClassName() {
		return className;
	}

	public void setClassName(String className) {
		this.className = className;
	}

	public Set<RoutingDefinition> getRoutingOut() {
		return routingOut;
	}

	public void setRoutingOut(Set<RoutingDefinition> routingOut) {
		this.routingOut = routingOut;
	}

	public Set<RoutingDefinition> getRoutingIn() {
		return routingIn;
	}

	public void setRoutingIn(Set<RoutingDefinition> routingIn) {
		this.routingIn = routingIn;
	}

	public String getClassConstruct() {
		return classConstruct;
	}

	public void setClassConstruct(String classConstruct) {
		this.classConstruct = classConstruct;
	}

	public String getClassDestruct() {
		return classDestruct;
	}

	public void setClassDestruct(String classDestruct) {
		this.classDestruct = classDestruct;
	}

	public String getName() {
		return name;
	}

	public void setName(String name) {
		this.name = name;
	}
}
