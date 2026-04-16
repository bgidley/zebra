/*
 * Copyright 2004 Anite - Central Government Division
 *    http://www.anite.com/publicsector
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.anite.antelope.zebra.factory;

import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Query;
import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import org.apache.avalon.framework.activity.Initializable;
import org.apache.avalon.framework.component.Component;
import org.apache.avalon.framework.configuration.Configurable;
import org.apache.avalon.framework.configuration.Configuration;
import org.apache.avalon.framework.configuration.ConfigurationException;
import org.apache.avalon.framework.context.Context;
import org.apache.avalon.framework.context.ContextException;
import org.apache.avalon.framework.context.Contextualizable;
import org.apache.avalon.framework.service.ServiceException;
import org.apache.avalon.framework.service.ServiceManager;
import org.apache.avalon.framework.service.Serviceable;
import org.apache.avalon.framework.thread.ThreadSafe;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;

import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessVersions;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.IXmlDefinition;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.xmlloader.LoadFromFile;

/**
 * Avalon Service to provide Zebra definitions to the engine. They are also
 * stored in the database which is useful for reporting
 * 
 * @author Eric Pugh
 * @author Ben Gidley
 *  
 */
public class AntelopeDefinitionsFactory implements IAvalonDefsFactory,
        ThreadSafe, Component, Configurable, Contextualizable, Initializable,
        Serviceable {

    /** logging */
    private static Log log = LogFactory
            .getLog(AntelopeDefinitionsFactory.class);

    /**
     * Application Root supplied via the Avalon context. This is filled by
     * Turbine when the avalon service is initialised. This is not necessarily
     * standard avalon behaviour
     */
    private String appRootPath = null;

    private ServiceManager manager;

    /* Variables for configuration */
    private String filePath;

    private String processDefinitionClass;

    private String taskDefinitionClass;

    private String processVersionsClass;

    private String propertyElementClass;

    private String propertyGroupsClass;

    private String routingDefinitionClass;

    /* Constants for configuration file */
    private static final String AVALON_CONF_BASE_FOLDER = "baseFolder";

    private static final String AVALON_CONF_PROCESSDEFCLASSNAME = "processDefinitionClass";

    private static final String AVALON_CONF_TASKDEFCLASSNAME = "taskDefinitionClass";

    private static final String AVALON_CONF_PROCESSVERSIONCLASSNAME = "processVersionsClass";

    private static final String AVALON_CONF_PROPERTYGROUPCLASSNAME = "propertyGroupsClass";

    private static final String AVALON_CONF_ROUTINGDEFCLASSNAME = "routingDefinitionClass";

    private static final String AVALON_CONF_PROPERTYELEMENTCLASSNAME = "propertyElementClass";

    /**
     * Zebra File Loaded
     */
    private LoadFromFile loadFromFile;

    /**
     * All the process definitions
     */
    private Map allProcessDefinitionsByName = new HashMap();

    private Map allProcessDefinitionsById = new HashMap();

    private Map allTaskDefinitionsById = new HashMap();

    public Map getAllProcessDefinitions() {

        return allProcessDefinitionsByName;
    }

    /**
     * gets a process definition for passed name
     */
    public IProcessDefinition getProcessDefinition(String name)
            throws DefinitionNotFoundException {

        IProcessDefinition processDefinition = (IProcessDefinition) allProcessDefinitionsByName
                .get(name);
        if (processDefinition == null) {
            throw new DefinitionNotFoundException();
        }
        return (processDefinition);
    }

    /**
     * Get a task definition
     */
    public ITaskDefinition getTaskDefinition(Long id)
            throws DefinitionNotFoundException {
        ITaskDefinition taskDefinition;

        /* First try and get it from cache - we have only
         Cached the most recent version - cos otherwise there 
         would be loads */

        taskDefinition = (ITaskDefinition) allTaskDefinitionsById.get(id);

        if (taskDefinition == null) {

            try {
                Session session = PersistenceLocator.getInstance()
                        .getCurrentSession();
                taskDefinition = (ITaskDefinition) session.get(
                        AntelopeTaskDefinition.class, id);
            } catch (Exception e) {
                log.error("Exception while loading task definition:" + id, e);
                throw new DefinitionNotFoundException(e);
            }
        }

        if (taskDefinition == null) {
            throw new DefinitionNotFoundException(
                    "Definition not found in DB or Cache:" + id.toString());
        }
        return taskDefinition;
    }

    /**
     * Checks to see if given definition is in the database
     * 
     * @param definition
     * @return @throws
     *         HibernateException
     * @throws PersistenceException
     */
    protected boolean checkIfXmlProcessDefinitionInDatabase(
            AntelopeProcessDefinition definition) throws HibernateException,
            PersistenceException {

        Query query = PersistenceLocator
                .getInstance()
                .getCurrentSession()
                .createQuery(
                        "from "
                                + AntelopeProcessDefinition.class.getName()
                                + " cpd where cpd.processVersions.name=:name and cpd.version = :version");
        query.setString("name", definition.getName());
        query.setLong("version", definition.getVersion().longValue());

        List q = query.list();
        if (q.size() == 1) {
            return true;
        }
        return false;

    }

    /**
     * Save an XML process definition
     * 
     * @param processDefinition
     * @throws HibernateException
     * @throws PersistenceException
     */
    protected void saveXmlProcessDefinitionInDatabase(
            AntelopeProcessDefinition processDefinition, Session session)
            throws HibernateException, PersistenceException {

        Transaction t = session.beginTransaction();

        initXmlSet(processDefinition.getRoutingDefinitions());

        for (Iterator i = processDefinition.getTaskDefinitions().iterator(); i
                .hasNext();) {
            AntelopeTaskDefinition taskDefinition = (AntelopeTaskDefinition) i
                    .next();
            initXmlId(taskDefinition);
            initXmlSet(taskDefinition.getRoutingOut());
            initXmlSet(taskDefinition.getRoutingIn());
        }
        AntelopeProcessVersions processVersions = findOrCreateProcessVersion(processDefinition
                .getName());
        processVersions.addProcessVersion(processDefinition);
        session.saveOrUpdate(processDefinition);
        t.commit();
    }

    /**
     * Finds/Creates a process version
     * @param name
     * @throws PersistenceException
     * @throws HibernateException
     */
    protected AntelopeProcessVersions findOrCreateProcessVersion(String name)
            throws PersistenceException, HibernateException {
        Session session = PersistenceLocator.getInstance().getCurrentSession();
        AntelopeProcessVersions processVersions = null;
        Query query = session.createQuery("from "
                + AntelopeProcessVersions.class.getName()
                + " apv where name=:name");
        query.setString("name", name);
        List q = query.list();
        if (q.size() > 1) {
            throw new PersistenceException(
                    "Found more then 1 AntelopeProcessVersions for name "
                            + name);
        } else if (q.size() == 1) {
            processVersions = (AntelopeProcessVersions) q.get(0);
        } else {
            processVersions = new AntelopeProcessVersions();
            processVersions.setName(name);
            session.save(processVersions);
        }
        return processVersions;
    }

    private void initXmlId(IXmlDefinition xmlDefinition) {
        xmlDefinition.setXmlId(xmlDefinition.getId());
        xmlDefinition.setId(null);
    }

    private void initXmlSet(Set xmlSet) {
        for (Iterator j = xmlSet.iterator(); j.hasNext();) {
            IXmlDefinition xmlDefinition = (IXmlDefinition) j.next();
            initXmlId(xmlDefinition);
        }
    }

    /**
     * Fetches the latest version of each process in a map
     * @return
     * @throws Exception
     */
    protected void getDistinctLatestVersions(Map nameMap, Map idMap)
            throws Exception {

        Session session = PersistenceLocator.getInstance().getCurrentSession();
        List results = session.find("from AntelopeProcessVersions");
        for (Iterator i = results.iterator(); i.hasNext();) {
            AntelopeProcessVersions antelopeProcessVersions = (AntelopeProcessVersions) i
                    .next();
            AntelopeProcessDefinition latestProcessDefinition = (AntelopeProcessDefinition) antelopeProcessVersions
                    .getLatestProcessVersion();
            nameMap.put(antelopeProcessVersions.getName(),
                    latestProcessDefinition);
            idMap.put(latestProcessDefinition.getId(), latestProcessDefinition);

            // Cache the last version's task defs only
            Iterator tasks = latestProcessDefinition.getTaskDefinitions()
                    .iterator();
            while (tasks.hasNext()) {
                AntelopeTaskDefinition taskDefinition = (AntelopeTaskDefinition) tasks
                        .next();
                allTaskDefinitionsById.put(taskDefinition.getId(),
                        taskDefinition);
            }
        }
    }

    /* Avalon Methods */
    /**
     * Initialize service
     */
    public void initialize() throws Exception {

        Session session = PersistenceLocator.getInstance().getCurrentSession();

        loadFromFile = new LoadFromFile();
        loadFromFile.setProcessDefinitionClass(Class
                .forName(processDefinitionClass));
        loadFromFile.setTaskDefinitionClass(Class.forName(taskDefinitionClass));
        loadFromFile.setProcessVersionsClass(Class
                .forName(processVersionsClass));
        loadFromFile.setPropertyElementClass(Class
                .forName(propertyElementClass));
        loadFromFile.setPropertyGroupsClass(Class.forName(propertyGroupsClass));
        loadFromFile.setRoutingDefinitionClass(Class
                .forName(routingDefinitionClass));

        loadFromFile.loadProcessDefs(appRootPath + filePath);

        for (Iterator i = loadFromFile.getAllProcessVersions().iterator(); i
                .hasNext();) {
            try {
                AntelopeProcessVersions processVersions = (AntelopeProcessVersions) i
                        .next();
                for (Iterator j = processVersions.getProcessVersions()
                        .iterator(); j.hasNext();) {
                    AntelopeProcessDefinition processDefinition = (AntelopeProcessDefinition) j
                            .next();
                    if (!checkIfXmlProcessDefinitionInDatabase(processDefinition)) {
                        saveXmlProcessDefinitionInDatabase(processDefinition,
                                session);
                    }
                }
            } catch (Exception e) {
                log.error(e);
                throw e;
            }
        }
        // Set up the two maps
        getDistinctLatestVersions(allProcessDefinitionsByName,
                allProcessDefinitionsById);
        // Close the session to make sure objects can be reconnected later
        session.close();
    }

    /**
     * Avalon configure
     */
    public void configure(Configuration configuration)
            throws ConfigurationException {
        log.debug("configure");
        filePath = configuration.getAttribute(AVALON_CONF_BASE_FOLDER);
        processDefinitionClass = configuration
                .getAttribute(AVALON_CONF_PROCESSDEFCLASSNAME);
        taskDefinitionClass = configuration
                .getAttribute(AVALON_CONF_TASKDEFCLASSNAME);
        processVersionsClass = configuration
                .getAttribute(AVALON_CONF_PROCESSVERSIONCLASSNAME);
        propertyElementClass = configuration
                .getAttribute(AVALON_CONF_PROPERTYELEMENTCLASSNAME);
        propertyGroupsClass = configuration
                .getAttribute(AVALON_CONF_PROPERTYGROUPCLASSNAME);
        routingDefinitionClass = configuration
                .getAttribute(AVALON_CONF_ROUTINGDEFCLASSNAME);
    }

    /**
     * Load the application path
     */
    public void contextualize(Context avalonContext) throws ContextException {
        log.debug("contextualize");
        appRootPath = (String) avalonContext
                .get(AvalonComponentService.COMPONENT_APP_ROOT);

    }

    /**
     * Used for quick access to the process definition
     */
    public IProcessDefinition getProcessDefinition(Long id)
            throws DefinitionNotFoundException {
        IProcessDefinition processDefinition = (IProcessDefinition) allProcessDefinitionsById
                .get(id);
        if (processDefinition == null) {
            throw new DefinitionNotFoundException();
        }
        return (processDefinition);
    }

    /** 
     * Get the service manager
     */
    public void service(ServiceManager manager) throws ServiceException {
        this.manager = manager;

    }
}