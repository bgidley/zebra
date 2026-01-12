package org.apache.fulcrum.hibernate.factory;

import java.util.Properties;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.ServiceImplementationFactory;
import org.hibernate.Session;

public class HibernateSessionFactoryTest extends TestCase {
    public void testInitialiseService() {
        
        HibernateSessionFactory hibernateSessionFactory = (HibernateSessionFactory) RegistryManager
                .getInstance().getRegistry().getService("fulcrum.hibernate.HibernateSessionFactory",
                        HibernateSessionFactory.class);
        assertNotNull(hibernateSessionFactory);

        Session session = (Session) hibernateSessionFactory.createCoreServiceImplementation(null);
        assertNotNull(session);
        Properties props = hibernateSessionFactory.getHibernateProperties();
        assertNotNull(props);
        System.out.println(props.toString());
    }
}
