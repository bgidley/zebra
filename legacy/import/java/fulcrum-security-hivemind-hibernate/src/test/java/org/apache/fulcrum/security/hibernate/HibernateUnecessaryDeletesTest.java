package org.apache.fulcrum.security.hibernate;

import junit.framework.TestCase;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.ModelManager;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.acl.AccessControlList;
import org.apache.fulcrum.security.model.dynamic.DynamicModelManager;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;
import org.hibernate.Session;

public class HibernateUnecessaryDeletesTest extends TestCase {
	private static final Log log = LogFactory
			.getLog(HibernateUnecessaryDeletesTest.class);

	public void setUp() throws Exception {
		// Force Registry to have test configuration
		Resource resource = new ClasspathResource(new DefaultClassResolver(),
				"META-INF/hivemodule_test.xml");
		RegistryManager.getInstance().getResources().add(resource);
		super.setUp();
	}

	public void testDuplicateSave() throws UnknownEntityException,
			DataBackendException, EntityDisabledException,
			EntityExistsException {

		UserManager userManager = (UserManager) RegistryManager.getInstance()
				.getRegistry().getService(UserManager.class);

		GroupManager groupManager = (GroupManager) RegistryManager
				.getInstance().getRegistry().getService(GroupManager.class);

		DynamicModelManager modelManager = (DynamicModelManager) RegistryManager
				.getInstance().getRegistry().getService(DynamicModelManager.class);

		DynamicGroup group = (DynamicGroup) groupManager
				.getGroupInstance("Bobbies");
		groupManager.addGroup(group);

		DynamicUser bobby = (DynamicUser) userManager.getUserInstance("bobby");
		userManager.addUser(bobby, "bobby");

		modelManager.grant(bobby, group);
		
		AccessControlList acl = userManager.getACL(bobby);

		Session session = (Session) RegistryManager.getInstance().getRegistry()
				.getService(Session.class);
		log.info("About to Flush, is dirty:" + session.isDirty());
		session.flush();
		log.info("Flushed");
		assertFalse(session.isDirty());

		assertNotNull(acl);
		log.info("Saving Bobby");
		//userManager.saveUser(bobby);

	}
}
