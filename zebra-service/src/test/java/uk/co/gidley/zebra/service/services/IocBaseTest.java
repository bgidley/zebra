package uk.co.gidley.zebra.service.services;

import org.apache.tapestry5.ioc.Registry;
import org.apache.tapestry5.ioc.RegistryBuilder;
import org.testng.annotations.AfterSuite;
import org.testng.annotations.BeforeSuite;
import uk.co.gidley.zebra.inmemory.services.InMemoryModule;

/**
 * Created by IntelliJ IDEA.
 * User: bgidley
 * Date: 29-Apr-2010
 * Time: 15:36:43
 */
public class IocBaseTest {
    Registry registry;

    @BeforeSuite
    public void beforeSuite() {

        RegistryBuilder builder = new RegistryBuilder();
        builder.add(InMemoryModule.class);
        Registry registry = builder.build();
        registry.performRegistryStartup();
        this.registry = registry;
    }

    @AfterSuite
    public void afterSuite() {
        if (registry != null) {
            registry.shutdown();
        }
    }
}
