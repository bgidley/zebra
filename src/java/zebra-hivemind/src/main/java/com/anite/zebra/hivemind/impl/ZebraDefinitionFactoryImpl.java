package com.anite.zebra.hivemind.impl;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

import javax.persistence.PersistenceException;

import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.hibernate.Criteria;
import org.hibernate.HibernateException;
import org.hibernate.Query;
import org.hibernate.Session;
import org.hibernate.Transaction;
import org.hibernate.criterion.Restrictions;

import com.anite.zebra.ext.xmlloader.LoadFromFile;
import com.anite.zebra.hivemind.api.ZebraDefinitionFactory;
import com.anite.zebra.hivemind.om.defs.IXmlDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraProcessDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraProcessVersions;
import com.anite.zebra.hivemind.om.defs.ZebraPropertyElement;
import com.anite.zebra.hivemind.om.defs.ZebraPropertyGroups;
import com.anite.zebra.hivemind.om.defs.ZebraRoutingDefinition;
import com.anite.zebra.hivemind.om.defs.ZebraTaskDefinition;

/**
 * This is the definitions factory service.
 * 
 * This is a Singleton Hivemind Service.
 * 
 * @author ben.gidley
 * 
 */
public class ZebraDefinitionFactoryImpl implements ZebraDefinitionFactory {
    /** logging */
    private static Log log = LogFactory.getLog(ZebraDefinitionFactoryImpl.class);

    /* Variables for configuration */
    private String processesPath;

    /**
     * Hibernate Session for loading definitions
     */
    private Session session;

    /**
     * All the process definitions
     */
    //private Map<String, ZebraProcessDefinition> allProcessDefinitionsByName = new HashMap<String, ZebraProcessDefinition>();
    //	private Map<Long, ZebraProcessDefinition> allProcessDefinitionsById = new HashMap<Long, ZebraProcessDefinition>();
    //private Map<Long, ZebraTaskDefinition> latestTaskDefinitionsById = new HashMap<Long, ZebraTaskDefinition>();
    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraDefinitionFactory#getTaskDefinition(java.lang.Long)
     */
    public ZebraTaskDefinition getTaskDefinition(Long id) {
        ZebraTaskDefinition taskDefinition;
        taskDefinition = (ZebraTaskDefinition) this.session.get(ZebraTaskDefinition.class, id);
        return taskDefinition;
    }

    /**
     * Checks to see if given definition is in the database
     * 
     * @param definition
     * @return
     * @throws HibernateException
     * @throws PersistenceException
     */
    protected boolean checkIfXmlProcessDefinitionInDatabase(ZebraProcessDefinition definition)
            throws HibernateException {

        Query query = this.session.createQuery("from " + ZebraProcessDefinition.class.getName()
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
    protected void saveXmlProcessDefinitionInDatabase(ZebraProcessDefinition processDefinition)
            throws HibernateException {

        Transaction t = this.session.beginTransaction();

        initXmlSet(processDefinition.getRoutingDefinitions());

        for (Iterator i = processDefinition.getTaskDefinitions().iterator(); i.hasNext();) {
            ZebraTaskDefinition taskDefinition = (ZebraTaskDefinition) i.next();
            initXmlId(taskDefinition);
            initXmlSet(taskDefinition.getRoutingOut());
            initXmlSet(taskDefinition.getRoutingIn());
        }
        ZebraProcessVersions processVersions = findOrCreateProcessVersion(processDefinition.getName());
        processVersions.addProcessVersion(processDefinition);
        this.session.saveOrUpdate(processDefinition);
        t.commit();
    }

    /**
     * Finds/Creates a process version
     * 
     * @param name
     * @throws PersistenceException
     * @throws HibernateException
     */
    protected ZebraProcessVersions findOrCreateProcessVersion(String name) throws HibernateException {

        ZebraProcessVersions processVersions = null;
        Query query = this.session
                .createQuery("from " + ZebraProcessVersions.class.getName() + " apv where name=:name");
        query.setString("name", name);
        List q = query.list();
        if (q.size() == 1) {
            processVersions = (ZebraProcessVersions) q.get(0);
        } else if (q.size() == 0) {
            processVersions = new ZebraProcessVersions();
            processVersions.setName(name);
            this.session.save(processVersions);
        } else {
            // More than 1 process with this name (this is impossible!)
            throw new NestableRuntimeException("There is more than one process with name:" + name);
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

    //    /**
    //     * Fetches the latest version of each process in a map
    //     * 
    //     * @return
    //     * @throws Exception
    //     */
    //    protected void getDistinctLatestVersions() throws Exception {
    //
    //        Query q = this.session.createQuery("from ZebraProcessVersions");
    //        List results = q.list();
    //        for (Iterator i = results.iterator(); i.hasNext();) {
    //            ZebraProcessVersions zebraProcessVersions = (ZebraProcessVersions) i.next();
    //            ZebraProcessDefinition latestProcessDefinition = (ZebraProcessDefinition) zebraProcessVersions
    //                    .getLatestProcessVersion();
    //            this.allProcessDefinitionsByName.put(zebraProcessVersions.getName(), latestProcessDefinition);
    //            this.allProcessDefinitionsById.put(latestProcessDefinition.getId(), latestProcessDefinition);
    //
    //            // Cache the last version's task defs only
    //            Iterator tasks = latestProcessDefinition.getTaskDefinitions().iterator();
    //            while (tasks.hasNext()) {
    //                ZebraTaskDefinition taskDefinition = (ZebraTaskDefinition) tasks.next();
    //                this.latestTaskDefinitionsById.put(taskDefinition.getId(), taskDefinition);
    //            }
    //        }
    //    }

    /**
     * Initialize service
     */
    public void initializeService() throws Exception {

        LoadFromFile loadFromFile = new LoadFromFile();
        loadFromFile.setProcessDefinitionClass(ZebraProcessDefinition.class);
        loadFromFile.setTaskDefinitionClass(ZebraTaskDefinition.class);
        loadFromFile.setProcessVersionsClass(ZebraProcessVersions.class);
        loadFromFile.setPropertyElementClass(ZebraPropertyElement.class);
        loadFromFile.setPropertyGroupsClass(ZebraPropertyGroups.class);
        loadFromFile.setRoutingDefinitionClass(ZebraRoutingDefinition.class);

        loadFromFile.loadProcessDefs(this.processesPath);

        for (Iterator i = loadFromFile.getAllProcessVersions().iterator(); i.hasNext();) {
            try {
                ZebraProcessVersions processVersions = (ZebraProcessVersions) i.next();
                for (Iterator j = processVersions.getProcessVersions().iterator(); j.hasNext();) {
                    ZebraProcessDefinition processDefinition = (ZebraProcessDefinition) j.next();
                    if (!checkIfXmlProcessDefinitionInDatabase(processDefinition)) {
                        saveXmlProcessDefinitionInDatabase(processDefinition);
                    }
                }
            } catch (Exception e) {
                log.error(e);
                throw e;
            }
        }
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraDefinitionFactory#getTaskDefinitionIds(java.lang.String, java.lang.String)
     */
    @SuppressWarnings("unchecked")
    public List<Long> getTaskDefinitionIds(String processName, String taskName) {
        StringBuffer sql = new StringBuffer();
        sql.append("SELECT td.id ");
        sql
                .append("FROM ZebraProcessDefinition pd, processTaskDefinitions ptd, ZebraTaskDefinition td, ZebraProcessVersions pv ");
        sql.append("WHERE pd.id=ptd.processDefinitionId ");
        sql.append("AND pd.versionId=pv.id ");
        sql.append("AND pd.id=ptd.processDefinitionId ");
        sql.append("AND ptd.taskDefinitionId=td.id ");
        sql.append("AND pv.name=:processName ");
        sql.append("AND td.name=:taskName");

        Query q = session.createSQLQuery(sql.toString());
        q.setString("processName", processName);
        q.setString("taskName", taskName);

        // Query stupidly returns a list of BigIntegers. 
        // Need to convert them into Longs. Yawn.
        List<BigInteger> results = q.list();
        List<Long> properResults = new ArrayList<Long>(results.size());
        for (BigInteger i : results) {
            properResults.add(i.longValue());
        }

        return properResults;
    }

    public Session getSession() {
        return this.session;
    }

    public void setSession(Session session) {
        this.session = session;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraDefinitionFactory#getProcessDefinitionById(java.lang.Long)
     */
    public ZebraProcessDefinition getProcessDefinitionById(Long id) {
        return (ZebraProcessDefinition) session.load(ZebraProcessDefinition.class, id);
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.hivemind.impl.ZebraDefinitionFactory#getProcessDefinitionByName(java.lang.String)
     */
    public ZebraProcessDefinition getProcessDefinitionByName(String name) {
        Criteria criteria = session.createCriteria(ZebraProcessVersions.class);
        criteria.add(Restrictions.eq("name", name));
        ZebraProcessVersions versions = (ZebraProcessVersions) criteria.uniqueResult();
        return (ZebraProcessDefinition) versions.getLatestProcessVersion();
        
    }

    /**
     * Use getTaskDefinition instead
     * @deprecated
     * @param id
     * @return
     */
    public ZebraTaskDefinition getTaskDefinitionById(Long id) {
        return this.getTaskDefinition(id);
    }

    public String getProcessesPath() {
        return this.processesPath;
    }

    public void setProcessesPath(String processesPath) {
        this.processesPath = processesPath;
    }

}
