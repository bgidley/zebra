package org.apache.fulcrum.hivemind;

import junit.framework.TestCase;

import org.apache.hivemind.ApplicationRuntimeException;
import org.apache.hivemind.Registry;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

public class RegistryManagerTest extends TestCase {

    /*
     * Test method for 'org.apache.fulcrum.hivemind.RegistryManager.getInstance()'
     */
    public void testGetInstance() {
        RegistryManager manager = RegistryManager.getInstance();
        assertNotNull(manager);
    }

    /*
     * Test method for 'org.apache.fulcrum.hivemind.RegistryManager.getRegistry()'
     */
    public void testGetRegistry() {
        Registry registry = RegistryManager.getInstance().getRegistry();
        assertNotNull(registry);
    }

    public void testResourceLoading() {

        RegistryManager.getInstance().rebuildRegistry();
        Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_hivemindtest.xml");
        RegistryManager.getInstance().getResources().add(resource);

        IDummy dummyService = (IDummy) RegistryManager.getInstance().getRegistry().getService(IDummy.class);
        
        assertNotNull(dummyService);
        
        RegistryManager.getInstance().rebuildRegistry();
        try {
            dummyService = (IDummy) RegistryManager.getInstance().getRegistry().getService(IDummy.class);
        } catch (ApplicationRuntimeException e) {
            return;
        }
        fail();
        
    }
}
