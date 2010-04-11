package org.apache.fulcrum.hibernate;


import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;
import org.hibernate.Session;
import org.hibernate.Transaction;

public class SessionTest extends TestCase{
    
    public void setUp() throws Exception {
        // Force Registry to have test configuration
        Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_hibernatetest.xml");
        RegistryManager.getInstance().getResources().add(resource);
        super.setUp();
    }
    
    public void testGetSession(){
        Session session = (Session) RegistryManager.getInstance().getRegistry().getService("fulcrum.hibernate.Session", Session.class);
        
        assertNotNull(session);
    }
    
    public void testInsert(){
        Session session = (Session) RegistryManager.getInstance().getRegistry().getService("fulcrum.hibernate.Session", Session.class);
        Sample sample = new Sample();
        Transaction t = session.beginTransaction();
        session.saveOrUpdate(sample);
        t.commit();        
        
    }

    public void testInsertAnnotation(){
        Session session = (Session) RegistryManager.getInstance().getRegistry().getService("fulcrum.hibernate.Session", Session.class);
        SampleAnnotation sample = new SampleAnnotation();
        Transaction t = session.beginTransaction();
        session.saveOrUpdate(sample);
        t.commit();        

    }
    
}
