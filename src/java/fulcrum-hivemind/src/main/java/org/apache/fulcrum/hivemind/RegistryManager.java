package org.apache.fulcrum.hivemind;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.hivemind.Registry;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.impl.RegistryBuilder;
import org.apache.hivemind.impl.XmlModuleDescriptorProvider;

public class RegistryManager {

    private static final Log log = LogFactory.getLog(RegistryManager.class);

    private Registry registry = null;

    private List<Resource> resources = new ArrayList<Resource>();

    private static RegistryManager _instance;

    private RegistryManager() {
        log.debug("Registry Manager Constructed");
    }

    /**
     * Build the registry, can be overridden to change how its created
     * @return
     */
    protected Registry constructRegistry() {
        log.debug("Constructing Registry (in call)");
        RegistryBuilder builder = new RegistryBuilder();

        builder.addDefaultModuleDescriptorProvider();

        if (resources.size() > 0) {
            builder.addModuleDescriptorProvider(new XmlModuleDescriptorProvider(new DefaultClassResolver(), resources));
        }

        return builder.constructRegistry(Locale.getDefault());

    }

    public static RegistryManager getInstance() {
        if (_instance == null) {
            log.debug("Constructing RegistryManager");
            _instance = new RegistryManager();
        }
        return _instance;
    }

    public synchronized Registry getRegistry() {
        if (this.registry == null) {
            log.debug("Constructing Registry");
            this.registry = constructRegistry();
            log.debug("Constructed Registry");
        }
        return this.registry;
    }

    public List<Resource> getResources() {
        return resources;
    }

    /**
     * Call the prior to first call to getInstance to override default module list
     * This is typically used in Unit Testing to swap an implementation
     * @param resources
     */
    public void setResources(List<Resource> resources) {
        this.resources = resources;
    }

    /**
     * Forces the registry to rebuild - used for unit testing
     *
     */
    public void rebuildRegistry() {

        this.resources.clear();
        if (this.registry != null) {
            this.registry.shutdown();
        }
        this.registry = null;
    }

}
