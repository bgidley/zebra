/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.manager;

import java.lang.reflect.ParameterizedType;

import org.apache.fulcrum.hivemind.RegistryManager;

import junit.framework.TestCase;

/**
 * Abstractly test if we an construct the serivces
 * 
 * Consider adding a CRUD test here - but it is hard to write with Generics and Hivemind proxis
 * 
 * @author ben.gidley
 *
 * @param <T>
 */
public abstract class BaseManagerTest<T extends BaseManager> extends TestCase {
	
	BaseManager manager;
	
	public void setUp(){
		manager = (T) RegistryManager.getInstance()
		.getRegistry().getService(getParameterClazz());
	}
	
	
	public void testService() {

		T service = (T) RegistryManager.getInstance()
				.getRegistry().getService(getParameterClazz());
		assertNotNull(service);
	}

	private Class getParameterClazz() {
		ParameterizedType ptype = (ParameterizedType) this.getClass()
				.getGenericSuperclass();
		return (Class) ptype.getActualTypeArguments()[0];
	}
	
	
}
