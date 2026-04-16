/*
 * Created on 24-May-2005
 */
package org.apache.fulcrum.hibernate.factory;

import java.util.Properties;

import javax.sql.DataSource;

import org.apache.commons.lang.StringUtils;
import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.hivemind.ServiceImplementationFactory;
import org.apache.hivemind.ServiceImplementationFactoryParameters;
import org.apache.hivemind.events.RegistryShutdownListener;
import org.apache.hivemind.service.ThreadCleanupListener;
import org.apache.hivemind.service.ThreadEventNotifier;
import org.hibernate.HibernateException;
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.cfg.AnnotationConfiguration;
import org.hibernate.cfg.Configuration;
import org.hibernate.connection.ConnectionProvider;
import org.hibernate.tool.hbm2ddl.SchemaExport;
import org.hibernate.tool.hbm2ddl.SchemaUpdate;

/**
 * Creates the Hibernate Session and manages the lifecycle.
 * 
 * The application simply gets the HibernateSession as a service on a Threaded
 * model.
 * 
 * @author Mike Jones
 * @author ben.gidley
 * 
 */
public class HibernateSessionFactory implements ServiceImplementationFactory,
		RegistryShutdownListener {

	private SessionFactory sessionFactory;

	private ThreadEventNotifier threadEventNotifier;

	private boolean updateSchema = false;

	private boolean createSchema = false;

	private DataSource connectionProviderDataSource = null;

	private Properties hibernateProperties = null;

	private String configXml;

	public void setConfigXml(String configXml) {
		this.configXml = configXml;
	}

	/**
	 * Called by factory when creating service
	 * 
	 */
	public void initializeService() {
		try {
			Configuration config = new AnnotationConfiguration();

			if (StringUtils.isEmpty(configXml)) {
				config.configure();
			} else {
				config.configure(configXml);
			}

			hibernateProperties = config.getProperties();
			if (createSchema) {
				SchemaExport export = new SchemaExport(config);
				export.drop(true, true);
				export.create(true, true);
			} else if (updateSchema) {
				new SchemaUpdate(config).execute(true, true);
			}
			sessionFactory = config.buildSessionFactory();
			ConnectionProvider connectionProvider = config.buildSettings()
					.getConnectionProvider();
			connectionProviderDataSource = new HibernateConnectionProviderDataSource(
					connectionProvider);
		} catch (HibernateException e) {
			e.printStackTrace();
			throw new NestableRuntimeException(e);
		}
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.hivemind.ServiceImplementationFactory#createCoreServiceImplementation(org.apache.hivemind.ServiceImplementationFactoryParameters)
	 */
	public Object createCoreServiceImplementation(
			ServiceImplementationFactoryParameters arg0) {
		try {
			Session session = sessionFactory.openSession();
			threadEventNotifier.addThreadCleanupListener(new SessionCloser(
					session));
			return session;
		} catch (HibernateException e) {
			throw new NestableRuntimeException(e);
		}

	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.hivemind.events.RegistryShutdownListener#registryDidShutdown()
	 */
	public void registryDidShutdown() {
		try {
			sessionFactory.close();
		} catch (HibernateException e) {
			throw new NestableRuntimeException(e);
		}
	}

	public void setThreadEventNotifier(ThreadEventNotifier notifier) {
		this.threadEventNotifier = notifier;
	}

	public void setUpdateSchema(boolean updateSchema) {
		this.updateSchema = updateSchema;
	}

	private class SessionCloser implements ThreadCleanupListener {
		private final Session session;

		public SessionCloser(Session session) {
			this.session = session;
		}

		public void threadDidCleanup() {
			try {
				session.close();
			} catch (HibernateException e) {
				throw new NestableRuntimeException(e);
			}
			threadEventNotifier.removeThreadCleanupListener(this);
		}
	}

	public boolean isCreateSchema() {
		return createSchema;
	}

	public void setCreateSchema(boolean createSchema) {
		this.createSchema = createSchema;
	}

	public DataSource getConnectionProviderDataSource() {
		return this.connectionProviderDataSource;
	}

	public Properties getHibernateProperties() {
		return this.hibernateProperties;
	}
}
