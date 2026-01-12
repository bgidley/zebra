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

package com.anite.zebra.core.definitions.api;


/**
 * @author Matthew Norris
 */
public interface IRoutingDefinition {
	/**
	 * @return the ID of this RoutingDefinition
	 */
	public Long getId();
	/**
	 * @return the Name of the Routing. Can be NULL
	 */
	public String getName();
	/**
	 * @return TRUE if the routing runs Parallel (i.e. split)
	 */
	public boolean getParallel();
	/**
	 * @return the name of the IConditionAction class the Engine 
	 * should call to determine whether this routing has run 
	 * or not. Can be NULL.
	 */
	public String getConditionClass();
	/**
	 * @return the Originating TaskDef
	 */
	public ITaskDefinition getOriginatingTaskDefinition();
	
	/**
	 * @return the Desintation TaskDef
	 */
	
	public ITaskDefinition getDestinationTaskDefinition();
}