/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.taskAction;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.hivemind.impl.Zebra;
import com.anite.zebra.hivemind.om.state.ZebraProcessInstance;
import com.anite.zebra.hivemind.util.RegistryHelper;

public class LogTaskActionTest  extends TestCase {
    protected void setUp() throws Exception {

        Resource resource = new ClasspathResource(new DefaultClassResolver(),
                "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);
    }

    public void testService() throws Exception {

        try {
            Zebra zebra = RegistryHelper.getInstance().getZebra();
            ZebraProcessInstance pi = zebra.createProcessPaused("testProcess");
            
            zebra.startProcess(pi);
        } catch (StartProcessException e) {
            e.printStackTrace();
        }        
    }
}
