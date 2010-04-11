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

import java.io.File;
import java.util.HashSet;
import java.util.Set;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.ext.definitions.api.IProcessVersions;

/**
 * @author matt
 */
public class LoadFromFile {

	private static final Log log = LogFactory.getLog(LoadFromFile.class);

	private Set allProcessVersions = new HashSet();

	private static final String PROCESSDEF_EXTENSION = ".acgwfd.xml";

	private Class processDefinitionClass;

	private Class taskDefinitionClass;

	private Class processVersionsClass;

	private Class propertyElementClass;

	private Class propertyGroupsClass;

	private Class routingDefinitionClass;

	public void loadProcessDef(File file) throws Exception {

		log.info("Reading Process Definition from:" + file.getAbsolutePath());
		processFile(file);
	}

	public void loadProcessDefs(String pathToScan) throws Exception {

		log.debug("finding processDefClass");
		File scanpath = new File(pathToScan);

		log.info("Reading Process Definitions from:"
				+ scanpath.getAbsolutePath());

		String[] subitems = scanpath.list();
		if (subitems != null) {
			for (int i = 0; i < subitems.length; i++) {
				File subitem = new File(scanpath, subitems[i]);
				if (subitem.isDirectory()) {
					try {
						processFolder(subitem);
					} catch (Exception e) {
						//ignore an error thrown by this, just log it
						log.debug(e);
						log.error("Failure processing folder " + subitem, e);
					}
				} else if (subitem.isFile()) {
					try {
						processFile(subitem);
					} catch (Exception e) {
						// ignore an error thrown by this, just log it
						log.debug(e);
						log.error("Failure processing file " + subitem, e);
					}
				}
			}
		} else {
			log.info("No Process Definitions in directory:" + pathToScan);
		}
	}

	/**
	 * @param string
	 *            The Folder to process
	 */
	private void processFolder(File folder) throws Exception {

		String[] subItems = folder.list();

		for (int i = 0; i < subItems.length; i++) {
			File subitem = new File(folder, subItems[i]);
			if (subitem.isDirectory()) {
				processFolder(subitem);
			} else {
				try {
					processFile(subitem);
				} catch (Exception e) {
					// ignore an error thrown by this, just log it
					log.debug(e);
					log.error("Failure processing file " + subitem, e);
				}
			}
		}
	}

	/**
	 * @param subitem
	 *            a file to process
	 */
	private void processFile(File subitem) throws Exception {
		log.debug("Processing: " + subitem.getName());
		XMLLoadProcess xmlLoadProcess = new XMLLoadProcess();
		if (subitem.getName().endsWith(PROCESSDEF_EXTENSION)) {
			xmlLoadProcess.setProcessDefinitionClass(processDefinitionClass);
			xmlLoadProcess.setTaskDefinitionClass(taskDefinitionClass);
			xmlLoadProcess.setProcessVersionsClass(processVersionsClass);
			xmlLoadProcess.setPropertyElementClass(propertyElementClass);
			xmlLoadProcess.setPropertyGroupsClass(propertyGroupsClass);
			xmlLoadProcess.setRoutingDefinitionClass(routingDefinitionClass);
			IProcessVersions processVersions = xmlLoadProcess
					.loadFromFile(subitem);
			// TODO dirty - needs to be fixed
			// iterate through and just keep latest version
			if (processVersions.getProcessVersions().size() > 0) {
				allProcessVersions.add(processVersions);
			}

		}

	}

	/**
	 * returns a full list of all processdefs
	 * 
	 * @return
	 */
	public Set getAllProcessVersions() {
		return this.allProcessVersions;
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
}