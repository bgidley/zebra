/*
 * Copyright 2004, 2005 Anite - Central Government Division
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
package com.anite.zebra.hivemind.api;

import org.hibernate.Session;

import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * The lock manager is responsible for creating/releasing locks
 * It must manage its own transactions if the database is used.
 * 
 * @author Ben
 *
 */
public interface LockManager {
	/**
	 * Aquire the lock for the passed process instance. If the lock cannot be aquired this should block until it 
	 * can.
	 * 
	 * It is up to the implementation to decide if it requires a timeout. In general timeouts should not occur as 
	 * the locks being aquired are short lived.
	 * 
	 * @param processInstance
	 * @param session
	 * @throws LockException
	 */
	public void aquireLock(IProcessInstance processInstance, Session session) throws LockException;

	/**
	 * Release the lock for the passed process instance
	 * @param processInstance
	 * @param session
	 * @throws LockException
	 */
	public void releaseLock(IProcessInstance processInstance, Session session) throws LockException;
}
