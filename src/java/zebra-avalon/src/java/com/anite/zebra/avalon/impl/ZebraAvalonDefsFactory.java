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
package com.anite.zebra.avalon.impl;

import java.util.Map;

import org.apache.avalon.framework.activity.Initializable;
import org.apache.avalon.framework.component.Component;
import org.apache.avalon.framework.configuration.Configurable;
import org.apache.avalon.framework.configuration.Configuration;
import org.apache.avalon.framework.configuration.ConfigurationException;
import org.apache.avalon.framework.context.Context;
import org.apache.avalon.framework.context.ContextException;
import org.apache.avalon.framework.context.Contextualizable;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;
import com.anite.zebra.ext.xmlloader.LoadFromFile;

/**
 * Mostly a sample, doesn't realy do anything.  Your environment 
 * will specifiy what you need.
 * 
 * @author eric.pugh
 * @author Matthew.Norris
 * 
 */
public class ZebraAvalonDefsFactory implements IAvalonDefsFactory,
        Initializable, Configurable, Contextualizable, Component {

    /**
     * logging
     */
    private static Log log = LogFactory.getLog(ZebraAvalonDefsFactory.class);

    private String appRootPath = null;

    private String filePath = null;

    /**
     * constant for "baseFolder"
     */
    private static final String AVALON_CONF_BASE_FOLDER = "baseFolder";

    private LoadFromFile lff = null;

    private String processDefClassName;

    private String taskDefClassName;

    /**
     * constant for "processDefClass"
     */
    private static final String AVALON_CONF_PROCESSDEFCLASSNAME = "processDefClass";

    /**
     * constant for "taskDefClass"
     */
    private static final String AVALON_CONF_TASKDEFCLASSNAME = "taskDefClass";


    public Map getAllProcessDefinitions() {
        return null;// lff.getAllProcessDefs();
    }

    public IProcessDefinition getProcessDefinition(String processName)
            throws DefinitionNotFoundException {
      
    	return null;
    }

    public IProcessDefinition getProcessDefinition(Long id) throws DefinitionNotFoundException {
        return null;
    }
    
    public ITaskDefinition getTaskDefinition(Long id) throws DefinitionNotFoundException {
        return null;
    }
    
    /*
     * 
     * AVALON STUFF
     *  
     */

    public void initialize() throws Exception {
        lff = new LoadFromFile();
        lff.setProcessDefinitionClass(ClassLoader.getSystemClassLoader().loadClass(processDefClassName));
        lff.setTaskDefinitionClass(ClassLoader.getSystemClassLoader().loadClass(taskDefClassName));
        lff.loadProcessDefs(appRootPath + filePath);
        
    }


    
    public void configure(Configuration arg0) throws ConfigurationException {
        // configure this loader
        log.debug("configure");
        filePath = arg0.getAttribute(AVALON_CONF_BASE_FOLDER);
        processDefClassName = arg0
                .getAttribute(AVALON_CONF_PROCESSDEFCLASSNAME);
        taskDefClassName = arg0.getAttribute(AVALON_CONF_TASKDEFCLASSNAME);

    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.avalon.framework.context.Contextualizable#contextualize(org.apache.avalon.framework.context.Context)
     */
    /**
     * {@inheritDoc}
     */
    public void contextualize(Context arg0) throws ContextException {
        // know where we are located
        log.debug("contextualize");
        appRootPath = (String) arg0.get("componentAppRoot");

    }

}
