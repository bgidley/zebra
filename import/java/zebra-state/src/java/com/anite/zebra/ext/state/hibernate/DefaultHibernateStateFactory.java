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
package com.anite.zebra.ext.state.hibernate;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;
import net.sf.hibernate.SessionFactory;
import net.sf.hibernate.cfg.Configuration;
import net.sf.hibernate.tool.hbm2ddl.SchemaExport;

import com.anite.zebra.core.factory.exceptions.StateFailureException;

/**
 * @author Eric Pugh
 * 
 * An implementation of the HibernateStateFactory that by default creates a
 * Session from /hibernate.cfg.xml. However, you can also pass in the Session to
 * use.
 */
public class DefaultHibernateStateFactory extends HibernateStateFactory {

    private Session session;

    /**
     * Allow an external session to be passed in. This prevents having to create
     * a new Session.
     * 
     * @param session
     */
    public void setSession(Session session) {
        this.session = session;
    }
    
    public Session getSession() throws StateFailureException {
        try {
            if (session == null) {
                Configuration configuration = new Configuration();
                SessionFactory hibernateSessionFactory = configuration
                        .configure().buildSessionFactory();
                session = hibernateSessionFactory.openSession();
                new SchemaExport(configuration).create(true, true);

            }
            return session;
        } catch (HibernateException e) {
            throw new StateFailureException(e);
        }
    }

    /**
     * Provide the locking class
     */
    public Class getLockClass() {
        return HibernateLock.class;
    }

}