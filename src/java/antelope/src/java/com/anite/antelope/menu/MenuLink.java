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



/**
 *
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 */
public class MenuLink extends MenuItem {    
    
    /**
     * The href that the menu will item will go to
     */
    protected String htmlHref = "#";
    
    /**
     * This is the value that will appear as the link for the menu
     */
    protected String value;

    /**
     * This method return the html for the menu item this is basically a link
     * with a given class. How this appears in the HTML should be set in the
     * CSS.
     * 
     * @return
     */
    public String draw() {
        StringBuffer sb = new StringBuffer();
        sb.append("<a ");
        buildParams(sb);
        sb.append(" >" +value+"</a>");
        
        return sb.toString();
    }    

    /**
     * 
     */
    public MenuLink() {
        super();
    }
    /**
     * @param value
     */
    public MenuLink(String value) {
        this.value = value;
    }
    
    /** 
     * Build a html link with the values held in this class
     * @return
     */
    protected void buildParams(StringBuffer sb) {
        super.buildParams(sb);
        sb.append(createParameter("href", htmlHref));
    }
   

    /**
     * @return Returns the href.
     */
    public String getHtmlHref() {
        return htmlHref;
    }

    /**
     * @param href
     *            The href to set.
     */
    public void setHtmlHref(String href) {
        this.htmlHref = href;
    }

    /**
     * @return Returns the value.
     */
    public String getValue() {
        return value;
    }

    /**
     * @param value
     *            The value to set.
     */
    public void setValue(String value) {
        this.value = value;
    }
}