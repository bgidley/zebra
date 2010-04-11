/*
 * Copyright 2005 Anite - Central Government Division
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
package org.apache.fulcrum.quartz.factory;

import java.io.IOException;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Properties;

import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.hibernate.factory.HibernateSessionFactory;
import org.apache.fulcrum.quartz.tables.CreatePostgresTables;
import org.apache.hivemind.ServiceImplementationFactory;
import org.apache.hivemind.ServiceImplementationFactoryParameters;
import org.apache.hivemind.events.RegistryShutdownListener;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.SchedulerFactory;
import org.quartz.impl.StdSchedulerFactory;

public class QuartzSchedulerFactory implements ServiceImplementationFactory, RegistryShutdownListener {

    private static final Log log = LogFactory.getLog(QuartzSchedulerFactory.class);

    private static final String HIBERNATE_DRIVER_KEY = "hibernate.connection.driver_class";

    private static final String HIBERNATE_PASSWORD_KEY = "hibernate.connection.password";

    private static final String HIBERNATE_URL_KEY = "hibernate.connection.url";

    private static final String HIBERNATE_USERNAME_KEY = "hibernate.connection.username";

    private static final String DEFAULT_MAX_CONNECTIONS = "27";

    /*
     * This class only supports use of the following databases/drivers
     * to support a new db, create a new class to create the tables using
     * Postgres ones as an example and add the appropriate 
     * block into the createTables method.
     */
    private static final String POSTGRESQL = "org.postgresql.Driver";

    private Scheduler scheduler = null;

    private HibernateSessionFactory hibernateSessionFactory = null;

    public HibernateSessionFactory getHibernateSessionFactory() {
        return hibernateSessionFactory;
    }

    public void setHibernateSessionFactory(HibernateSessionFactory hibernateSessionFactory) {
        this.hibernateSessionFactory = hibernateSessionFactory;
    }

    public Object createCoreServiceImplementation(ServiceImplementationFactoryParameters arg0) {

        if (scheduler == null) {
            try {
                /*
                 * check and see if we have scheduler tables in the DB.
                 */
                Properties hibernateProperties = hibernateSessionFactory.getHibernateProperties();
                String driver = hibernateProperties.getProperty(HIBERNATE_DRIVER_KEY);
                log.debug("url:" + hibernateProperties.getProperty(HIBERNATE_URL_KEY));
                log.debug("username:" + hibernateProperties.getProperty(HIBERNATE_USERNAME_KEY));
                log.debug("password:" + hibernateProperties.getProperty(HIBERNATE_PASSWORD_KEY));
                checkTables(driver);
                Properties defaults = new Properties();
                defaults.load(this.getClass().getResourceAsStream("/quartz.properties"));
                defaults.put("org.quartz.dataSource.quartzDS.driver", hibernateProperties
                        .getProperty(HIBERNATE_DRIVER_KEY));
                defaults.put("org.quartz.dataSource.quartzDS.URL", hibernateProperties.getProperty(HIBERNATE_URL_KEY));
                defaults.put("org.quartz.dataSource.quartzDS.user", hibernateProperties
                        .getProperty(HIBERNATE_USERNAME_KEY));
                defaults.put("org.quartz.dataSource.quartzDS.password", hibernateProperties
                        .getProperty(HIBERNATE_PASSWORD_KEY));
                defaults.put("org.quartz.dataSource.quartzDS.maxConnections", DEFAULT_MAX_CONNECTIONS);
                log.info(defaults.toString());
                SchedulerFactory schedulerFactory = new StdSchedulerFactory(defaults);
                scheduler = schedulerFactory.getScheduler();
                scheduler.start();
            } catch (IOException ioe) {
                throw new NestableRuntimeException(ioe);
            } catch (SchedulerException se) {
                throw new NestableRuntimeException(se);
            } catch (SQLException sqle) {
                log.error("SQLException caught:", sqle);
                throw new NestableRuntimeException(sqle);
            }
        }

        return scheduler;
    }

    public void registryDidShutdown() {
        try {
            scheduler.shutdown();
            scheduler = null;
        } catch (SchedulerException se) {
            throw new NestableRuntimeException(se);
        }

    }

    /**
     * method to check the JobStore to see if tables exist and if not create
     * them.
     */
    private void checkTables(String driverClassName) throws SQLException {
        Connection conn = hibernateSessionFactory.getConnectionProviderDataSource().getConnection();
        String query = "select * from qrtz_job_details;";
        try {
            /*
             * we are not interested in the result just whether an
             * exception is thrown on a table not found
             */
            Statement stmt = conn.createStatement();
            stmt.execute(query);
        } catch (SQLException sqle) {
            /*
             * no table.
             */
            createTables(conn, driverClassName);
        }
    }

    /**
     * creates the tables for the Quartz jobStore.
     */
    private void createTables(Connection conn, String driver) throws SQLException {
        if (POSTGRESQL.equalsIgnoreCase(driver)) {
            CreatePostgresTables tableCreator = new CreatePostgresTables();
            tableCreator.createTables(conn);
            return;
        }
        throw new RuntimeException("Driver not recognised as Postgres:" + driver);
    }

}
