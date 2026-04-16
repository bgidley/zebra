/*
 * Copyright 2004 Anite - Central Government Division
 * http://www.anite.com/publicsector
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License. You may obtain a copy of
 * the License at
 * 
 * http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */
package com.anite.antelope.modules.tools;

import junit.framework.TestCase;

import org.apache.turbine.util.TurbineConfig;
/**
 *
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones</a>
 *
 */
public class SecurityToolTest extends TestCase {

    private TurbineConfig tc;
    
    public void setUp() {
        
         tc =
            new TurbineConfig(
                    ".",
            "/src/test/CompleteTurbineResources.properties");
        tc.initialize();
    }
    
    public void tearDown() throws Exception
    {
        if (tc != null)
        {
            tc.dispose();
        }
    }

    
    public void testSecurityTool() {
    	
        
    }
    
    


}
