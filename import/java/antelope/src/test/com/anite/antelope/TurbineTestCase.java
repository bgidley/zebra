/*
 * Copyright 2004 Anite - Central Government Division
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

package com.anite.antelope;

import junit.framework.TestCase;

import org.apache.turbine.util.TurbineConfig;

/**
 * Extend this to make sure Turbine has started
 * @author Ben.Gidley
 */
public class TurbineTestCase extends TestCase {    
    
    public static void initialiseTurbine(){
                
        // Initialise Fake Turbine so it can resolve Avalon
        // In theory calling this twice should only initialise once
		TurbineConfig config = null;
		config = new TurbineConfig("./src/webapp/", "WEB-INF/conf/TurbineResources.properties");
		config.initialize();
    }
}
