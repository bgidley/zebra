package uk.co.gidley.zebra.service.services;

import org.apache.tapestry5.ioc.Registry;
import org.apache.tapestry5.ioc.RegistryBuilder;
import org.testng.annotations.AfterSuite;
import org.testng.annotations.BeforeSuite;
import uk.co.gidley.zebra.inmemory.services.InMemoryModule;
import uk.co.gidley.zebra.service.om.definitions.ProcessDefinition;
import uk.co.gidley.zebra.service.om.definitions.ProcessVersion;

import java.util.HashSet;

/**
 * Created by IntelliJ IDEA.
 * User: bgidley
 * Date: 29-Apr-2010
 * Time: 15:36:43
 */
public class IocBaseTest {
    Registry registry;
    private long id = 1L;

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

    protected ProcessVersion generateProcessVersion(String versionName) {
        ProcessVersion processVersions = new ProcessVersion();
        processVersions.setId(getNextId());
        processVersions.setName(versionName);
        processVersions.setProcessVersions(new HashSet<ProcessDefinition>());

        for (int version = 1; version <= 2; version++){
            generateProcessDefinition(processVersions, version);
        }


        return processVersions;
    }

    private void generateProcessDefinition(ProcessVersion processVersions, long version) {
        ProcessDefinition processDefinition = new ProcessDefinition();
        processDefinition.setId(getNextId());
        processDefinition.setProcessVersions(processVersions);
        processVersions.getProcessVersions().add(processDefinition);
        processDefinition.setVersion(version);
    }

    private long getNextId() {
        return id++;
    }
}
