package org.apache.fulcrum.security.model.test;

import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.List;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.hibernate.PersistenceHelper;
import org.apache.fulcrum.security.hibernate.dynamic.model.HibernateDynamicUser;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;
import org.hibernate.Query;
import org.hibernate.Session;

public class DatabaseWriteThroughTest extends TestCase {
	
	public static final String USER_NAME = "rich28";

	public void setUp() throws Exception {
		// Force Registry to have test configuration
		Resource resource = new ClasspathResource(new DefaultClassResolver(),
				"META-INF/hivemodule_test.xml");
		RegistryManager.getInstance().getResources().add(resource);
		super.setUp();
	}

	public void testAddUser() throws Exception {
		PersistenceHelper persistenceHelper = (PersistenceHelper) RegistryManager
				.getInstance().getRegistry()
				.getService(PersistenceHelper.class);

		
		HibernateDynamicUser user = new HibernateDynamicUser();
		user.setName(USER_NAME);
		user.setPassword("password");
		user.setLoginAttempts(0);
		user.setLockTime(0);

		Calendar date = Calendar.getInstance();
		GregorianCalendar passwordExpiry = new GregorianCalendar(date.get(Calendar.YEAR),
                												 date.get(Calendar.MONTH),
                												 date.get(Calendar.DAY_OF_MONTH));
		passwordExpiry.add(Calendar.DAY_OF_MONTH, 28);
		user.setPasswordExpiryDate(passwordExpiry.getTime());

		user.setPasswordExpiryDate(passwordExpiry.getTime());
		
		//Session session = persistenceHelper.retrieveSession();
        //Transaction transaction = session.beginTransaction();
        //session.save(user);
        //transaction.commit();
		persistenceHelper.addEntity(user);
	}
	
	public void testChangeUser() throws Exception {
		PersistenceHelper persistenceHelper = (PersistenceHelper) RegistryManager
		.getInstance().getRegistry()
		.getService(PersistenceHelper.class);
		
		Session session = persistenceHelper.retrieveSession();
		
		Query query = session.createQuery("from HibernateDynamicUser hdu where hdu.name=:name");
		query.setString("name", USER_NAME);
		
		List users = query.list();
		HibernateDynamicUser user = (HibernateDynamicUser) users.get(0);
		user.setPassword("changed");
        //Transaction transaction = session.beginTransaction();
        //session.saveOrUpdate(user);
        //transaction.commit();
		persistenceHelper.updateEntity(user);
	}
	
	public void testGetUserFromManager() throws Exception {
		SecurityService securityService = (SecurityService) RegistryManager.getInstance().getRegistry().getService(SecurityService.class);
        UserManager userManager = securityService.getUserManager();
        HibernateDynamicUser user = (HibernateDynamicUser) userManager.getUser(USER_NAME);
        user.setPassword("changed_2");
        user.setLoginAttempts(1);
        
        userManager.saveUser(user);

		/*PersistenceHelper persistenceHelper = (PersistenceHelper) RegistryManager
		.getInstance().getRegistry()
		.getService(PersistenceHelper.class);
		persistenceHelper.updateEntity(user);*/
	}
}
