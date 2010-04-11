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

package com.anite.zebra.core.factory.api;

import com.anite.zebra.core.api.IConditionAction;
import com.anite.zebra.core.api.IProcessConstruct;
import com.anite.zebra.core.api.IProcessDestruct;
import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.api.ITaskConstruct;
import com.anite.zebra.core.factory.exceptions.ClassInstantiationException;

/**
 * Called by the Engine whenever it requires an instance 
 * of a given class (e.g. a ProcessConstruct class)
 * 
 * Can be used to implement a custom class loading or pooling mechanism.
 * 
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public interface IClassFactory {
	/**
	 * Returns an instance of the named ProcessConstruct class
	 * @param className
	 * @return an instance of the IProcessConstruct
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public IProcessConstruct getProcessConstruct(String className) throws ClassInstantiationException ;
	/**
	 * Returns an instance of the named ProcessDestruct class
	 * @param className
	 * @return an instance of the IProcessDestruct
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public IProcessDestruct getProcessDestruct(String className) throws ClassInstantiationException;
	/**
	 * Returns an instance of the named ConditionAction class
	 * @param className
	 * @return an instance of the IConditionAction
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public IConditionAction getConditionAction(String className) throws ClassInstantiationException;
	/**
	 * Returns an instance of the named TaskAction class
	 * @param className
	 * @return an instance of the ITaskAction
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public ITaskAction getTaskAction(String className) throws ClassInstantiationException;
	/**
	 * Returns an instance of the named TaskConstruct class
	 * @param className
	 * @return an instance of the ITaskConstruct
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public ITaskConstruct getTaskConstruct(String className) throws ClassInstantiationException;
}
