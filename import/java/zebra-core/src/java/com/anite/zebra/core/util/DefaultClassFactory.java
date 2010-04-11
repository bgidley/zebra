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

package com.anite.zebra.core.util;

import com.anite.zebra.core.api.IConditionAction;
import com.anite.zebra.core.api.IProcessConstruct;
import com.anite.zebra.core.api.IProcessDestruct;
import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.api.ITaskConstruct;
import com.anite.zebra.core.factory.api.IClassFactory;
import com.anite.zebra.core.factory.exceptions.ClassInstantiationException;

/**
 * Default implementation of the ClassFactory.
 * If not ClassFactory is passed into the construction of the Engine
 * this class is used instead.
 * 
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class DefaultClassFactory implements IClassFactory {

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IClassFactory#getProcessConstruct(java.lang.String)
	 */
	public IProcessConstruct getProcessConstruct(String className)
			throws ClassInstantiationException {
		return (IProcessConstruct) getClass(className);
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IClassFactory#getProcessDestruct(java.lang.String)
	 */
	public IProcessDestruct getProcessDestruct(String className)
			throws ClassInstantiationException {
		return (IProcessDestruct) getClass(className);
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IClassFactory#getConditionAction(java.lang.String)
	 */
	public IConditionAction getConditionAction(String className)
			throws ClassInstantiationException {
		return (IConditionAction) getClass(className);
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IClassFactory#getTaskAction(java.lang.String)
	 */
	public ITaskAction getTaskAction(String className)
			throws ClassInstantiationException {
		return (ITaskAction) getClass(className);
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IClassFactory#getTaskConstruct(java.lang.String)
	 */
	public ITaskConstruct getTaskConstruct(String className)
			throws ClassInstantiationException {
		return (ITaskConstruct) getClass(className);
	}
	
	/**
	 * A very basic class constructor routine.
	 * 
	 * @param className name of class to instantiate
	 * @return an instance of the class
	 * @throws ClassInstantiationException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public Object getClass(String className) throws ClassInstantiationException {
		Class theClass;
		try {
			theClass = this.getClass().getClassLoader().loadClass(className);
			return theClass.newInstance();
		} catch (Exception e) {
			String emsg = "Failed to instance class " + className;
			throw new ClassInstantiationException(emsg,e);
		}
		
	}

}
