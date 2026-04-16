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
package com.anite.zebra.hivemind.impl;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.hivemind.Resource;
import org.apache.hivemind.impl.DefaultClassResolver;
import org.apache.hivemind.util.ClasspathResource;

public class ZebraSubflowsTest extends TestCase {
   private Zebra zebra;
    
    protected void setUp() throws Exception {
        Resource resource = new ClasspathResource(new DefaultClassResolver(), "META-INF/hivemodule_zebradefinitions.xml");
        RegistryManager.getInstance().getResources().add(resource);
        
        
        this.zebra = (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra",Zebra.class);
    }
    
//    public void testSubflows() throws CreateProcessException, StartProcessException{
//        
//        ZebraProcessInstance zpi = zebra.createProcessPaused("SubProcessReturnTop");
//        
//        assertNotNull(zpi);
//        zebra.startProcess(zpi);
//        
//        assertEquals(3,zpi.getHistoryInstances().size());
//        
//    }
}
