package com.anite.zebra.hivemind.impl;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

public class DefaultZebraImplTest extends TestCase {

    public void setUp() {
        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);
    }

    public void testInitialiseHiveMind() {
        Zebra zebra = (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra", Zebra.class);

        assertNotNull(zebra);
        assertNotNull(zebra.getDefinitionFactory());

    }
}
