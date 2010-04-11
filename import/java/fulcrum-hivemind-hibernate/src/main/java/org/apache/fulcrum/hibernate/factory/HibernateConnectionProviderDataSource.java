package org.apache.fulcrum.hibernate.factory;

import java.io.PrintWriter;
import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.apache.commons.lang.NotImplementedException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.connection.ConnectionProvider;

public class HibernateConnectionProviderDataSource implements DataSource {

	private ConnectionProvider connectionProvider = null;
	
	private static final Log log = LogFactory.getLog(HibernateConnectionProviderDataSource.class);
	
	public HibernateConnectionProviderDataSource(ConnectionProvider cp)
	{
		this.connectionProvider = cp;
	}
	
	public Connection getConnection() throws SQLException {
		return connectionProvider.getConnection();
	}

	public Connection getConnection(String username, String password) throws SQLException {
		log.warn("Not implemented by ConnectionProvider. Username/password ignored. getConnection() called.");
		return this.connectionProvider.getConnection();
	}

	public PrintWriter getLogWriter() throws SQLException {
		throw new NotImplementedException("getLogWriter() is not implemented by this DataSource.");
	}

	public void setLogWriter(PrintWriter out) throws SQLException {
		throw new NotImplementedException("setLogWriter() is not implemented by this DataSource.");
		
	}

	public void setLoginTimeout(int seconds) throws SQLException {
		throw new NotImplementedException("setLoginTimeout is not implemented by this DataSource.");
		
	}

	public int getLoginTimeout() throws SQLException {
		throw new NotImplementedException("getLoginTimeout() is not implemented by this DataSource.");
	}

}
