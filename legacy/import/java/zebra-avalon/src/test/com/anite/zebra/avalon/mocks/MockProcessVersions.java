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
package com.anite.zebra.avalon.mocks;

import java.util.Set;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.ext.definitions.api.IProcessVersion;
import com.anite.zebra.ext.definitions.api.IProcessVersions;

/**
 * @author Eric Pugh
 *
 */
public class MockProcessVersions implements IProcessVersions {

    /* (non-Javadoc)
     * @see com.anite.zebra.ext.definitions.api.IProcessVersions#getLatestProcessVersion()
     */
    public IProcessVersion getLatestProcessVersion() {
        return null;
    }
    /* (non-Javadoc)
     * @see com.anite.zebra.ext.definitions.api.IProcessVersions#getName()
     */
    public String getName() {
        return null;
    }
    /* (non-Javadoc)
     * @see com.anite.zebra.ext.definitions.api.IProcessVersions#getProcessVersions()
     */
    public Set getProcessVersions() {
        return null;
    }
    public MockProcessVersions() {
        super();
    }

    public Set getProcessDefs() {
        return null;
    }

    public void addProcessDef(IProcessDefinition arg0) {

    }

    public IProcessDefinition getLatestProcessDef() {
        return null;
    }

}
