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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.services.pull.ApplicationTool;

import com.anite.antelope.menu.Menu;

/**
 * The class is basically a fascade to to functions that are
 * held in the menu class.
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 * 
 */
public class MenuTool implements ApplicationTool {
    
    private static Log log = LogFactory.getLog(MenuTool.class);
    
    /**
     * The name to get the tool out of the context
     */
    public final static String DEFAULT_TOOL_NAME = "security";
    
    private Menu menu;

	/**
	 * This method is called after every request
	 */
	public void init(Object data) {
		
		
		log.info("Menu tool initialising");
		// if the menu has alread been build dont bother
		// doing it again
		if(menu==null) {
			menu = new Menu();			
		}		
		log.info("Menu built");		
	}

	/** 
	 * This method is NOT called after every request It should 
	 * only be used for development purposes!!!!!!!!!!
	 */
	public void refresh() {
		
	}
	
	public String draw() {
	    return menu.draw();
	}
}
