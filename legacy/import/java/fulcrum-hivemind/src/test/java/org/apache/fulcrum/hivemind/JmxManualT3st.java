package org.apache.fulcrum.hivemind;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

import junit.framework.TestCase;

import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

/**
 * A test to start JMX
 * 
 * This is run maunally
 * 
 * @author ben.gidley
 *
 */
public class JmxManualT3st extends TestCase {

    public void testManualConsoleConnect() throws IOException{
        RegistryManager.getInstance().rebuildRegistry();
        Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_hivemindtest.xml");
        RegistryManager.getInstance().getResources().add(resource);
        resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_jmx.xml");
        RegistryManager.getInstance().getResources().add(resource);

        IDummy dummyService = (IDummy) RegistryManager.getInstance().getRegistry().getService(IDummy.class);
        
        assertNotNull(dummyService);
        
        System.out.print("Press enter when done");
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        String inString = in.readLine();
        assertNotNull(inString);
      
    }
    
}
