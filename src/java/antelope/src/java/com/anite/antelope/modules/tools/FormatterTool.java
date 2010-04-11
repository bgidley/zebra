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

import java.sql.Date;
import java.sql.Time;
import java.text.DecimalFormat;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.services.pull.ApplicationTool;

import com.anite.antelope.utils.CalendarHelper;


/**
 * A tool for formatting dates and numbers.
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 * 
 */
public class FormatterTool implements ApplicationTool {
    
    private static Log log = LogFactory.getLog(FormatterTool.class);
    
    /**
     * The name to get the tool out of the context
     */
    public final static String DEFAULT_TOOL_NAME = "formatter";

	/**
	 * This method is called after every request
	 */
	public void init(Object data) {
		log.info("Formatter tool initialising");
	}
	
	public String getFormattedDate(Date theDate){
	    return CalendarHelper.getInstance().getFormattedDate(theDate);
	}
	
	public String getFormattedDateTime(java.util.Date theDate){
	    return CalendarHelper.getInstance().getFormattedDateTime(theDate);
	}
	
	public String getFormattedTime(Time theTime){
	    return CalendarHelper.getInstance().getFormattedTime(theTime);
	}
	
	public String getFormattedMoney(Double value) {
	    
        DecimalFormat nf = new DecimalFormat("##,###,##0.00");

 	    return nf.format(value);
	}

	/** 
	 * This method is NOT called after every request It should 
	 * only be used for development purposes!!!!!!!!!!
	 */
	public void refresh() {
		
	}
}
