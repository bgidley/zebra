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

package com.anite.zebra.core.factory;

import java.util.HashMap;
import java.util.Map;

import com.anite.zebra.core.api.IConditionAction;
import com.anite.zebra.core.api.IProcessConstruct;
import com.anite.zebra.core.api.IProcessDestruct;
import com.anite.zebra.core.api.ITaskAction;
import com.anite.zebra.core.api.ITaskConstruct;
import com.anite.zebra.core.factory.api.IClassFactory;
import com.anite.zebra.core.factory.exceptions.ClassInstantiationException;
import com.anite.zebra.core.util.DefaultClassFactory;

/**
 * test class for a cached class loader
 * 
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class CachedClassFactory implements IClassFactory {

	private DefaultClassFactory dcf = new DefaultClassFactory();
	private Map cache = new HashMap();
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
	 * 
	 * @param className
	 * @return
	 * @throws ClassInstantiationException
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	private Object getClass(String className) throws ClassInstantiationException {
		Object rtn = cache.get(className);
		if (rtn==null) {
			rtn = dcf.getClass(className);
			cache.put(className,rtn);
		}
		return rtn;
	}
	
	/**
	 * Forces the cache to flush all objects
	 *
	 * @author Matthew.Norris
	 * Created on Aug 21, 2005
	 */
	public void flushCache() {
		this.cache = new HashMap();
	}
}
