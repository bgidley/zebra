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

package com.anite.antelope.menu;

import org.apache.commons.lang.StringUtils;

/**
 * This class represents an item within a menu
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike </a>
 *  
 */
public abstract class MenuItem {

    /**
     * This is the id that will be used in hibernate
     */
    private long id;
    
    /**
     * The html id this is used for the drop down option of this menu
     */
    protected String htmlId;
    
    /**
     * This is the css class that will be applided to the menu
     */
    protected String htmlClass;


    /**
     * This method return the html for the menu item this is basically a link
     * with a given class. How this appears in the HTML should be set in the
     * CSS.
     * 
     * @return
     */
    public abstract String draw();
    
    /**
     * 
     * @return
     */    
    protected void buildParams(StringBuffer sb) {
        // only add the params if they have been set
        if(!StringUtils.isEmpty(htmlId)) {
            sb.append(createParameter("id", htmlId));
        }
        if(!StringUtils.isEmpty(htmlClass)) {
            sb.append(createParameter("class", htmlClass));
        }
    }
    
    protected String createParameter(String name, String value) {
        return name +"=\""+value+"\" ";        
    }
   

    /**
     * @return Returns the id.
     */
    public String getHtmlId() {
        return htmlId;
    }

    /**
     * @param id
     *            The id to set.
     */
    public void setHtmlId(String id) {
        this.htmlId = id;
    }

    /**
     * @return Returns the cssClass.
     */
    public String getHtmlClass() {
        return htmlClass;
    }

    /**
     * @param cssClass
     *            The cssClass to set.
     */
    public void setHtmlClass(String cssClass) {
        this.htmlClass = cssClass;
    }
}