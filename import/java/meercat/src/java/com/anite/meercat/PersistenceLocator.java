/*
 * Copyright 2004 Anite - Central Government Division
 * http://www.anite.com/publicsector
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

package com.anite.meercat;

import net.sf.hibernate.FlushMode;
import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;
import net.sf.hibernate.SessionFactory;
import net.sf.hibernate.cfg.Configuration;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * Provide Access to the Hibernate Session A Hibernate Session is attatched to
 * the thread of the current request. It is assumed (which is true in Tomcat)
 * that a request remains on the same thread throughout. If this is not true the
 * results will be undefined.
 * 
 */
public class PersistenceLocator {

    /**
     * The private singleton variable
     */
    private static PersistenceLocator instance;

    private static Log log = LogFactory.getLog(PersistenceLocator.class);

    /**
     * Holds the hibernate session on a per thread basis
     */
    private ThreadLocal threadLocal;

    /**
     * The system wide hibernate session factory
     */
    private SessionFactory hibernateSessionFactory;

    /**
     * The variable in the HTTP Session to bind the hibernate session to
     */
    public static final String SESSION_HIBERNATE_SESSION = "com.anite.meercat.hibernatesession";

    /**
     * Private Constructor to prevent construction
     */
    private PersistenceLocator() {
        if (threadLocal == null) {
            threadLocal = new ThreadLocal();
        }
    }

    /**
     * Singleton access method
     * 
     * @return
     */
    public static PersistenceLocator getInstance() {
        if (instance == null) {
            instance = new PersistenceLocator();
        }
        return instance;
    }

    /**
     * Gets the current session only based on the thread local
     * 
     * @return @throws
     *         PersistenceException
     */
    public synchronized Session getCurrentSession() throws PersistenceException {
        log.debug("Called currentSession()");

        Session session = (Session) threadLocal.get();
        if (session == null) {
            log.warn("Had to create a session as there wasn't one");
            session = openSession();
            threadLocal.set(session);

        }
        session = checkSessionIsOpen(session);
        return session;
    }

    /**
     * Checks if passed session is open
     * 
     * @param session
     * @throws PersistenceException
     */
    private Session checkSessionIsOpen(Session session)
            throws PersistenceException {
        log.debug("Called checkSessionIsOpen");
        
        if (!session.isOpen()){
            // Some hooligan has closed the session - this should not really happen - but can in unit tests
            log.info("Session was closed - creating a new one");
            session = openSession();
            threadLocal.set(session);
            
        }
        
        if (!session.isConnected()) {
            try {
                log.debug("Reconnecting Session");
                session.reconnect();
            } catch (HibernateException e) {
                if (!e.getMessage().equalsIgnoreCase(
                        "Session already connected")) {
                    log.error("Unable to reconnect", e);
                    throw new PersistenceException("Unable to reconnect", e);
                } else {
                    log
                            .debug("Apparently the session is actually connected.  Ignoring an \"Unable to reconnect\" error.");
                }
            }
        }
        if (log.isDebugEnabled()) {
            log.debug("Hibernate Session:" + session.toString());
        }
        return session;
    }

    /**
     * Opens a new hibernate session
     * 
     * @return @throws
     *         PersistenceException
     */
    private synchronized Session openSession() throws PersistenceException {
        try {
            log.debug("Called openSession()");

            Session session = getSessionFactory().openSession();
            session.setFlushMode(FlushMode.COMMIT);
            return session;

        } catch (Exception e) {
            log.error("Could not open hibernate session", e);
            throw new PersistenceException("Could not save.", e);
        }
    }

    /**
     * Tidies up between requests
     */
    protected synchronized void closeRequest() {
        Session session = (Session) threadLocal.get();
        if (session != null) {
            try {
                if (session.isConnected()) {
                    log.info("Closing Session");

                    // need this "clear" statement in case there are invalid
                    // objects hanging around that need to be saved
                    session.clear();
                    session.close();

                }
            } catch (HibernateException e) {
                log.error("Unable to close", e);
            }
        }
        threadLocal.set(null);
    }

    /**
     * Provides a shared connection factory
     * 
     * @return @throws
     *         PersistenceException
     */
    public synchronized SessionFactory getSessionFactory()
            throws PersistenceException {
        if (hibernateSessionFactory == null) {
            Configuration configuration = new Configuration();
            try {
                hibernateSessionFactory = configuration.configure()
                        .buildSessionFactory();
            } catch (HibernateException e) {
                log.error(e);
                throw new PersistenceException(
                        "Unable to configure session factory");
            }
        }
        return hibernateSessionFactory;
    }

}