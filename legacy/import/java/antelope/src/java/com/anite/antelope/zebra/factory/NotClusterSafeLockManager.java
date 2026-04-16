/*
 * Created on 09-Feb-2005
 */
package com.anite.antelope.zebra.factory;

import java.util.HashSet;
import java.util.Set;

import net.sf.hibernate.Session;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.ext.state.hibernate.LockManager;

/**
 * A in memory lock manager
 * THIS IS NOT AT ALL CLUSTER SAFE
 * So if you run it in a cluster it will break horribly
 * However it is far far quicker that doing it in the DB
 * @author Ben.Gidley
 */
public class NotClusterSafeLockManager extends LockManager {
    private Set locks = new HashSet();

    private final static Log log = LogFactory
            .getLog(NotClusterSafeLockManager.class);

    public void aquireLockImpl(IProcessInstance processInstance,
            Session session, Class clazz) throws LockException {

        boolean isLocked = false;
        while (!isLocked) {

            synchronized (locks) {
                if (locks.contains(processInstance.getProcessInstanceId())) {
                    // Locked
                } else {
                    locks.add(processInstance.getProcessInstanceId());
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

    public void releaseLockImpl(IProcessInstance processInstance, Session arg1, Class arg2)
            throws LockException {

        synchronized (locks){        
            locks.remove(processInstance.getProcessInstanceId());
        }
    }
}