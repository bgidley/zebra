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
package com.anite.zebra.hivemind.impl;

import java.util.HashSet;
import java.util.Set;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.Session;

import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.hivemind.api.LockManager;

/**
 * An in memory lock manager THIS IS NOT AT ALL CLUSTER SAFE So if you run it in
 * a cluster it will break horribly However it is far far quicker that doing it
 * in the DB
 * 
 * @author Ben.Gidley
 */
public class NotClusterSafeLockManager implements LockManager {
	private Set<Long> locks = new HashSet<Long>();

	private final static Log log = LogFactory
			.getLog(NotClusterSafeLockManager.class);

	public void aquireLock(IProcessInstance processInstance, Session session)
			throws LockException {

		boolean isLocked = false;
		while (!isLocked) {

			synchronized (this.locks) {
				if (this.locks.contains(processInstance.getProcessInstanceId())) {
					// Locked
				} else {
					this.locks.add(processInstance.getProcessInstanceId());
					isLocked = true;
				}
			}

			if (!isLocked) {
				try {
					Thread.sleep(10);
				} catch (InterruptedException e1) {
					log
							.error(
									"Interupted while trying to lock - this should not occur",
									e1);
					throw new LockException(e1);
				}
			}

		}

	}

	public void releaseLock(IProcessInstance processInstance, Session arg1)
			throws LockException {

		synchronized (this.locks) {
			this.locks.remove(processInstance.getProcessInstanceId());
		}
	}
}