/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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

package com.anite.zebra.ext.xmlloader;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.UnsupportedEncodingException;
import java.net.MalformedURLException;
import java.util.Iterator;

import org.apache.commons.lang.StringUtils;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.dom4j.DocumentException;
import org.dom4j.DocumentHelper;
import org.dom4j.io.DOMWriter;
import org.dom4j.io.OutputFormat;
import org.dom4j.io.SAXReader;
import org.dom4j.io.XMLWriter;
import org.w3c.dom.Document;
import org.w3c.dom.Node;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.ext.definitions.api.AbstractProcessDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.api.IProcessVersions;
import com.anite.zebra.ext.definitions.api.IPropertyGroupsAware;
import com.anite.zebra.ext.definitions.impl.PropertyElement;
import com.anite.zebra.ext.definitions.impl.PropertyGroups;
import com.anite.zebra.ext.definitions.impl.RoutingDefinition;
import com.anite.zebra.ext.definitions.impl.TaskDefinition;

/**
 * @author matt
 * @author Eric.Pugh
 */
public class XMLLoadProcess {
    private static final Log log = LogFactory.getLog(XMLLoadProcess.class);

    private static final String XMLNODE_TYPE = "ACGWFDNative";

    private static final String XMLATTR_VERSION = "Version";

    private static final String XMLNODE_VERSIONS = "ProcessVersions";

    private static final String XMLNODE_PROVER = "ProcessVersion";

    private static final String XMLATTR_PROVER = "VersionID";

    private static final String VERSIONLOAD = "3.0";

    private static final String XMLNODE_PROCESSDEF = "ProcessDef";

    private static final String XMLNODE_PROPS = "properties";

    private static final String XMLATTR_NAME = "name";

    private static final String XMLATTR_VALUE = "value";

    private static final String PROP_SYS = "(General)";

    private static final String XMLNODE_TASKDEFS = "TaskDefs";

    private static final String XMLNODE_TASKDEF = "TaskDef";

    private static final String XMLNODE_ROUTINGDEFS = "RoutingDefs";

    private static final String XMLNODE_ROUTINGDEF = "RoutingDef";

    private static final String XMLATTR_GUID = "GUID";

    private static final String PROP_SYNCHRONISE = "Synchronise";

    private static final String PROP_AUTO = "Auto";

    private static final String PROP_CLASSNAME = "Class Name";

    private static final String PROP_NAME = "Name";

    private static final String XMLATTR_TASKORGGUID = "TaskOrgGUID";

    private static final String XMLATTR_TASKDESTGUID = "TaskDestGUID";

    private static final String PROP_PARALLEL = "Parallel";

    private static final String PROP_CONSTRUCT = "Class Construct";

    private static final String PROP_DESTRUCT = "Class Destruct";

    private static final String PROP_CONDITIONCLASS = "Condition Class";

    private static final String XMLATTR_FIRSTTASK = "FirstTask";

    private Class processDefinitionClass;

    private Class taskDefinitionClass;

    private Class processVersionsClass;

    private Class propertyElementClass;

    private Class propertyGroupsClass;

    private Class routingDefinitionClass;

    /**
     * loads an XML process definition
     * 
     * @param xmlFile
     *            xml file to load
     * @param processDefClass
     *            class to use for ProcessDefinition (IProcessDef)
     * @param taskDefClass
     *            class to use for TaskDefinition (ITaskDef)
     * @return an instance of the processDefClass with all the Process information loaded into it
     * @throws Exception
     */
    public IProcessVersions loadFromFile(File xmlFile) throws Exception {
        log.debug("Processing XML in " + xmlFile.getName());

        checkProperties();

        Document doc = readDocument(xmlFile);
        Node root = doc.getFirstChild();

        try {
            return processHeader(root);
        } catch (Exception e) {
            log.error(e);
            e.printStackTrace();
            throw e;
        }

    }

    protected void checkProperties() throws Exception {
        if (processDefinitionClass == null) {
            throw new Exception("processDefinitionClass missing");
        } else if (taskDefinitionClass == null) {
            throw new Exception("taskDefinitionClass missing");
        } else if (processVersionsClass == null) {
            throw new Exception("processVersionsClass missing");
        } else if (propertyElementClass == null) {
            throw new Exception("propertyElementClass missing");
        } else if (propertyGroupsClass == null) {
            throw new Exception("propertyGroupsClass missing");
        } else if (routingDefinitionClass == null) {
            throw new Exception("routingDefinitionClass missing");
        }
    }

    /**
     * Read in a file of XML, strip out the pretty printing via some juggling of objects and then return a
     * org.w3.document DOM object.
     * 
     * @param xmlFile
     *            The file to be read in.
     * @return A ready to use org.w3.Document with pretty printing stripped out.
     * @throws DocumentException
     * @throws MalformedURLException
     * @throws UnsupportedEncodingException
     * @throws IOException
     */
    private Document readDocument(File xmlFile) throws DocumentException, MalformedURLException,
            UnsupportedEncodingException, IOException {
        SAXReader xmlReader = new SAXReader();
        xmlReader.setStripWhitespaceText(true);

        org.dom4j.Document dom4jDocument = xmlReader.read(xmlFile);

        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        OutputFormat format = OutputFormat.createCompactFormat();
        XMLWriter writer = new XMLWriter(baos, format);

        writer.write(dom4jDocument);

        dom4jDocument = DocumentHelper.parseText(baos.toString());

        DOMWriter domWriter = new DOMWriter();
        Document doc = domWriter.write(dom4jDocument);
        return doc;
    }

    private IProcessVersions processHeader(Node root) throws Exception {
        IProcessVersions processVersions = (IProcessVersions) processVersionsClass.newInstance();
        log.debug("processHeader " + root);
        if (root.getNodeName().compareTo(XMLNODE_TYPE) != 0) {
            throw new BadXMLException("Not a Process Def");
        }

        if (!compareNodeAttr(root, XMLATTR_VERSION, VERSIONLOAD)) {
            throw new Exception("Unable to load Process Def with Version " + getAttr(root, XMLATTR_VERSION));
        }

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_VERSIONS) == 0) {
                loadProcessVersion(node, processVersions);
            }
        }
        return processVersions;
    }

    private void loadProcessVersion(Node root, IProcessVersions processVersions) throws Exception {
        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_PROVER) == 0) {
                IProcessVersion pv;
                try {
                    pv = iterateProcessNodes(node.getFirstChild(), new Long(getAttr(node, XMLATTR_PROVER)),
                            processVersions);
                    processVersions.addProcessVersion(pv);
                } catch (NumberFormatException e) {
                    log.info(
                            "Unable to interate over a version - will continue with other versions - this one will be ingnored:"
                                    + processVersions.getName(), e);
                } catch (Exception e) {
                    if (i == 0) {
                        log
                                .debug("Unable to interate over a version - this is normal if it is the first version in a file:"
                                        + processVersions.getName());
                    } else {
                        log.info(
                                "Unable to interate over a version - will continue with other versions - this one will be ingnored:"
                                        + processVersions.getName(), e);
                    }
                }
            }
        }
    }

    public IProcessVersion iterateProcessNodes(Node root, Long version, IProcessVersions processVersions)
            throws Exception {

        log.debug("iterateProcessNodes " + root);
        if (root.getNodeName().compareTo(XMLNODE_PROCESSDEF) != 0) {
            throw new BadXMLException("Expected node " + XMLNODE_PROCESSDEF);
        }

        AbstractProcessDefinition pd = (AbstractProcessDefinition) processDefinitionClass.newInstance();

        pd.setVersion(version);
        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);

            if (node.getNodeName().compareTo(XMLNODE_PROPS) == 0) {
                // property group
                processPDPropGroup(node, pd, processVersions);
            } else if (node.getNodeName().compareTo(XMLNODE_TASKDEFS) == 0) {
                // TasksDefs
                processTaskDefs(node, pd);
            } else if (node.getNodeName().compareTo(XMLNODE_ROUTINGDEFS) == 0) {
                // RoutingDefs
                processRoutingDefs(node, pd);
            }
        }

        createRoutingLinks(pd);

        // this bit here may throw an exception if the First Task is not set in
        // the process definition
        pd.setFirstTask((TaskDefinition) pd.getTaskDefs().getTaskDef(new Long(getAttr(root, XMLATTR_FIRSTTASK))));

        //pd.setId(makeLongGuid(getAttr(root,XMLATTR_GUID)));
        return pd;
    }

    /**
     * turns a string representation of a guid into a Long
     * 
     * @param guid
     * @return
     */
    private Long makeLongGuid(String guid) {
        return new Long(guid);
    }

    private void createRoutingLinks(IProcessDefinition pd) {
        // now add outbound routings to each taskdef
        if (log.isDebugEnabled()) {
            log.debug("createRoutingLinks ");
        }

        for (Iterator it = pd.getRoutingDefs().iterator(); it.hasNext();) {
            IRoutingDefinition rd = (IRoutingDefinition) it.next();
            ITaskDefinition td = rd.getOriginatingTaskDefinition();
            td.getRoutingOut().add(rd);
            td = rd.getDestinationTaskDefinition();
            td.getRoutingIn().add(rd);
        }
    }

    private void processRoutingDefs(Node root, AbstractProcessDefinition pd) throws Exception {
        log.debug("processRoutingDefs");

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_ROUTINGDEF) != 0) {
                throw new BadXMLException("Expected node " + XMLNODE_ROUTINGDEF);
            }
            IRoutingDefinition rd = iterateRoutingDefNodes(node, pd);
            pd.getRoutingDefinitions().add(rd);
        }
    }

    private IRoutingDefinition iterateRoutingDefNodes(Node root, AbstractProcessDefinition pdd) throws Exception {
        RoutingDefinition rd = (RoutingDefinition) routingDefinitionClass.newInstance();
        rd.setId(makeLongGuid(getAttr(root, XMLATTR_GUID)));
        Long origTDId = makeLongGuid(getAttr(root, XMLATTR_TASKORGGUID));
        Long destTDId = makeLongGuid(getAttr(root, XMLATTR_TASKDESTGUID));
        rd.setOriginatingTaskDefinition(pdd.getTaskDefs().getTaskDef(origTDId));
        rd.setDestinationTaskDefinition(pdd.getTaskDefs().getTaskDef(destTDId));

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_PROPS) == 0) {
                // property group
                processRDPropGroup(node, rd);
            }
        }
        return rd;
    }

    private void processRDPropGroup(Node root, RoutingDefinition rd) throws Exception {
        log.debug("processRDPropGroup " + root);
        if (compareNodeAttr(root, XMLATTR_NAME, PROP_SYS)) {
            // system property
            processRDSysProps(root, rd);
        } else {
            // other property group

            processPropertyGroup(root, rd);

        }
    }

    private void processPropertyGroup(Node root, IPropertyGroupsAware ipga) throws Exception {

        createPropertyGroupsIfRequired(ipga);

        String groupName = getAttr(root, XMLATTR_NAME);

        log.debug("processPropertyGroup " + groupName);

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            String key = getAttr(node, XMLATTR_NAME);
            String value = getAttr(node, XMLATTR_VALUE);
            PropertyElement pe = (PropertyElement) propertyElementClass.newInstance();
            pe.setGroup(groupName);
            pe.setKey(key);
            pe.setValue(value);
            ((PropertyGroups) ipga.getPropertyGroups()).addPropertyElement(pe);

        }
    }

    private void processRDSysProps(Node root, RoutingDefinition rd) throws Exception {
        log.debug("processRDSysProps" + root);
        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (isNamedProp(node, PROP_NAME)) {
                rd.setName(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_PARALLEL)) {
                rd.setParallel(getLenientBoolean(getAttr(node, XMLATTR_VALUE)).booleanValue());
            } else if (isNamedProp(node, PROP_CONDITIONCLASS)) {
                rd.setConditionClass(getAttr(node, XMLATTR_VALUE));
            }
        }
    }

    private void processTaskDefs(Node root, AbstractProcessDefinition pd) throws Exception {
        log.debug("processTaskDefs ");

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_TASKDEF) != 0) {
                throw new BadXMLException("Expected node " + XMLNODE_TASKDEF);
            }
            TaskDefinition td = iterateTaskDefNodes(node);
            pd.getTaskDefinitions().add(td);
        }
    }

    private TaskDefinition iterateTaskDefNodes(Node root) throws Exception {
        TaskDefinition td = (TaskDefinition) taskDefinitionClass.newInstance();

        td.setId(makeLongGuid(getAttr(root, XMLATTR_GUID)));

        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (node.getNodeName().compareTo(XMLNODE_PROPS) == 0) {
                // property group
                processTDPropGroup(node, td);
            }
        }
        return td;
    }

    private void processTDPropGroup(Node root, TaskDefinition td) throws Exception {
        log.debug("processTDPropGroup" + root);
        if (compareNodeAttr(root, XMLATTR_NAME, PROP_SYS)) {
            // system property
            processTDSysProps(root, td);
        } else {
            // other propertygroup

            processPropertyGroup(root, td);

        }
    }

    private void processTDSysProps(Node root, TaskDefinition td) throws Exception {
        log.debug("processTDSysProps" + root);
        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (isNamedProp(node, PROP_NAME)) {
                td.setName(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_SYNCHRONISE)) {
                td.setSynchronise(getLenientBoolean(getAttr(node, XMLATTR_VALUE)).booleanValue());
            } else if (isNamedProp(node, PROP_AUTO)) {
                td.setAuto(getLenientBoolean(getAttr(node, XMLATTR_VALUE)));
            } else if (isNamedProp(node, PROP_CLASSNAME)) {
                td.setClassName(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_CONSTRUCT)) {
                td.setClassConstruct(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_DESTRUCT)) {
                td.setClassDestruct(getAttr(node, XMLATTR_VALUE));
            }
        }
    }

    private void processPDPropGroup(Node root, AbstractProcessDefinition pd, IProcessVersions processVersions)
            throws Exception {
        log.debug("processPDPropGroup" + root);
        if (compareNodeAttr(root, XMLATTR_NAME, PROP_SYS)) {
            // system property
            processPDSysProps(root, pd, processVersions);
        } else {
            // other property group

            processPropertyGroup(root, pd);
        }
    }

    private void createPropertyGroupsIfRequired(IPropertyGroupsAware ipga) throws Exception {
        if (ipga.getPropertyGroups() == null) {
            PropertyGroups pg = (PropertyGroups) propertyGroupsClass.newInstance();
            ipga.setPropertyGroups(pg);
        }

    }

    private void processPDSysProps(Node root, AbstractProcessDefinition pd, IProcessVersions processVersions)
            throws Exception {
        log.debug("processPDSysProps" + root);
        for (int i = 0; i < root.getChildNodes().getLength(); i++) {
            Node node = root.getChildNodes().item(i);
            if (isNamedProp(node, PROP_NAME)) {
                processVersions.setName(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_CONSTRUCT)) {
                pd.setClassConstruct(getAttr(node, XMLATTR_VALUE));
            } else if (isNamedProp(node, PROP_DESTRUCT)) {
                pd.setClassDestruct(getAttr(node, XMLATTR_VALUE));
            }
        }
    }

    private boolean isNamedProp(Node node, String value) throws Exception {
        return (getAttr(node, XMLATTR_NAME).equalsIgnoreCase(value));
    }

    private boolean compareNodeAttr(Node node, String attrName, String value) throws Exception {
        return (getAttr(node, attrName).compareTo(value) == 0);
    }

    private String getAttr(Node node, String name) throws Exception {
        String nodeValue = node.getAttributes().getNamedItem(name).getNodeValue();
        if (StringUtils.isEmpty(nodeValue)) {
            return null;
        } else {
            return nodeValue;
        }
    }

    private Boolean getLenientBoolean(String bool) {

        if (bool != null
                && (bool.equalsIgnoreCase("yes") || bool.equalsIgnoreCase("true") || bool.equalsIgnoreCase("on")
                        || bool.equalsIgnoreCase("1") || bool.equalsIgnoreCase("-1"))) {
            return Boolean.TRUE;
        } else {
            return Boolean.FALSE;
        }
    }

    /**
     * @param propertyElementClass
     *            The propertyElementClass to set.
     */
    public void setPropertyElementClass(Class propertyElementClass) {
        this.propertyElementClass = propertyElementClass;
    }

    /**
     * @param propertyGroupsClass
     *            The propertyGroupsClass to set.
     */
    public void setPropertyGroupsClass(Class propertyGroupsClass) {
        this.propertyGroupsClass = propertyGroupsClass;
    }

    /**
     * @param routingDefinitionClass
     *            The routingDefinitionClass to set.
     */
    public void setRoutingDefinitionClass(Class routingDefinitionClass) {
        this.routingDefinitionClass = routingDefinitionClass;
    }

    /**
     * @param taskDefinitionClass
     *            The taskDefinitionClass to set.
     */
    public void setTaskDefinitionClass(Class taskDefinitionClass) {
        this.taskDefinitionClass = taskDefinitionClass;
    }

    /**
     * @param processDefinitionClass
     *            The processDefinitionClass to set.
     */
    public void setProcessDefinitionClass(Class processDefinitionClass) {
        this.processDefinitionClass = processDefinitionClass;
    }

    /**
     * @param processVersionsClass
     *            The processVersionsClass to set.
     */
    public void setProcessVersionsClass(Class processVersionsClass) {
        this.processVersionsClass = processVersionsClass;
    }
}