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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.HibernateException;
import org.hibernate.Session;
import org.hibernate.Transaction;

import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.hivemind.api.LockManager;
import com.anite.zebra.hivemind.om.state.DatabaseLock;

/**
 * Locking code extracted from StateFactory into a Helper for profiling
 * 
 * @author Ben.Gidley
 */
public class ClusterSafeLockManager implements LockManager {

    private final static Log log = LogFactory.getLog(ClusterSafeLockManager.class);

    /**
     * @param processInstance
     * @throws LockException
     */
    public void aquireLock(IProcessInstance processInstance, Session session) throws LockException {
        boolean isLocked = false;
        while (!isLocked) {
            DatabaseLock lock;
            try {
                lock = (DatabaseLock) session.get(DatabaseLock.class, processInstance.getProcessInstanceId());
                if (lock != null) {
                    session.evict(lock);
                }
            } catch (HibernateException e2) {
                log.error("Unable to test for lock", e2);
                throw new LockException(e2);
            }
            if (lock == null) {
                try {
                    Class lockClazz = DatabaseLock.class;

                    lock = (DatabaseLock) lockClazz.newInstance();
                    lock.setProcessInstanceId(processInstance.getProcessInstanceId());

                    Transaction t = session.beginTransaction();
                    session.save(lock);
                    t.commit();
                    isLocked = true;
                } catch (HibernateException e) {
                    // It is vaguely possible someone beat us to it
                    try {
                        lock = null;
                        Thread.sleep(100);
                    } catch (InterruptedException e1) {
                        log.error("Interupted while trying to lock - this should not occur", e1);
                        throw new LockException(e1);
                    }
                } catch (InstantiationException e) {
                    log.error("Unable to create lock class", e);
                    throw new LockException(e);
                } catch (IllegalAccessException e) {
                    log.error("Unable to create lock class", e);
                    throw new LockException(e);
                }
            } else {
                try {
                    Thread.sleep(100);
                } catch (InterruptedException e1) {
                    log.error("Interupted while trying to lock - this should not occur", e1);
                    throw new LockException(e1);
                }
            }
        }
    }

    /**
     * @param processInstance
     * @throws LockException
     */
    public void releaseLock(IProcessInstance processInstance, Session session) throws LockException {

        try {
            DatabaseLock lock = (DatabaseLock) session.load(DatabaseLock.class, processInstance.getProcessInstanceId());
            Transaction t = session.beginTransaction();
            session.delete(lock);
            t.commit();

        } catch (HibernateException e) {
            log.error("Releasing Lock should never fail ", e);
            throw new LockException(e);
        }
    }

}