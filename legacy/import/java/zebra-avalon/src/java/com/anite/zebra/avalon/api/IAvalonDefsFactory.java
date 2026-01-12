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

package com.anite.zebra.avalon.api;

import java.util.Map;

import org.apache.avalon.framework.component.Component;
import org.apache.avalon.framework.thread.ThreadSafe;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.DefinitionNotFoundException;


/**
 * @author matt Note: need to extend Component to work in Avalon and ThreadSafe
 *         so we are a shared object
 */
public interface IAvalonDefsFactory extends Component,
        ThreadSafe {

    /** Avalon role - used to id the component within the manager */
    public static final String ROLE = IAvalonDefsFactory.class.getName();

    /**
     * returns all process defs stored in this factory
     * 
     * @return
     */
    public Map getAllProcessDefinitions();

    /**
     * returns a process definition by its name
     * @param processName process Name
     * @throws DefinitionNotFoundException definition not found exception
     */
    public IProcessDefinition getProcessDefinition(String processName)
            throws DefinitionNotFoundException;
    
    /**
     * returns a process definition by its id
     * @param processName process Name
     * @throws DefinitionNotFoundException definition not found exception
     */
    public IProcessDefinition getProcessDefinition(Long id)
            throws DefinitionNotFoundException;    
    
    /**
     * returns a task definition by its id
     * @throws DefinitionNotFoundException definition not found exception
     */
    public ITaskDefinition getTaskDefinition(Long id)
            throws DefinitionNotFoundException;       

}
