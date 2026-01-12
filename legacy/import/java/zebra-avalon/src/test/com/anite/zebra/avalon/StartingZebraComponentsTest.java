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
package com.anite.zebra.avalon;

import org.apache.fulcrum.testcontainer.BaseUnitTest;

import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.factory.api.IStateFactory;


/**
 * @author Steve.Cowx
 *
 * Test the remote service impl
 */
public class StartingZebraComponentsTest extends BaseUnitTest {

    
    /**
     * @param arg0
     */
    public StartingZebraComponentsTest(String arg0) {
        super(arg0);
    }
    

    public void testStartingServices() throws Exception
    {
        IStateFactory service = (IStateFactory)lookup(IStateFactory.class.getName());
        assertNotNull(service);
        IEngine engine = (IEngine)lookup(IEngine.class.getName());
        assertNotNull(engine);
        IAvalonDefsFactory defsFactory = (IAvalonDefsFactory)lookup(IAvalonDefsFactory.class.getName());
        
        this.release(defsFactory);
   
    }
}
