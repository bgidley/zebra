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

import org.apache.avalon.framework.activity.Initializable;
import org.apache.avalon.framework.service.ServiceException;
import org.apache.avalon.framework.service.ServiceManager;
import org.apache.avalon.framework.service.Serviceable;
import org.apache.avalon.framework.thread.ThreadSafe;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.ITaskInstance;

/**
 * @author matt This class handles transitioning the process
 */
public class ZebraAvalonEngine implements IEngine, Serviceable,
        Initializable, ThreadSafe {

    /**
     * logging
     */
    private static final Log log = LogFactory.getLog(ZebraAvalonEngine.class);

    private IEngine engine = null;

    private ServiceManager sm = null;

    public void transitionTask(ITaskInstance taskInstance)
            throws TransitionException {

        // ensure this class isn't instanced outside of the Avalon framework
        if (sm == null || engine == null) { throw new TransitionException(
                "Cannot use this component outside the Avalon framework"); }
        engine.transitionTask(taskInstance);
    }

    public IProcessInstance createProcess(IProcessDefinition processDef)
            throws CreateProcessException {
        return (engine.createProcess(processDef));
    }

    
    public void startProcess(IProcessInstance processInstance)
            throws StartProcessException {
        engine.startProcess(processInstance);
    }

    /*
     * 
     * AVALON STUFF BELOW
     * 
     *  
     */
   
    public void service(ServiceManager arg0) throws ServiceException {
        // Avalon calls this method to give us a Service Manager to find other
        // Avalon Components we ma
        sm = arg0;
    }

   
    public void initialize() throws Exception {
        log.info("Initializing " + this.getClass().getName());
        
       // zaff = (IAvalonFactoryFinder) sm.lookup(IAvalonFactoryFinder.ROLE);
        IStateFactory stateFactory= (IStateFactory)sm.lookup(IStateFactory.class.getName());
        engine = new Engine(stateFactory);
    }

}
