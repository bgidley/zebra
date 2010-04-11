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

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * This class is a representation for the menu.
 * TODO this should really be part of the heirachy of menu objecsts
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 *
 */
public class Menu {
    
    private static Log log = LogFactory.getLog(Menu.class);
    
    // this is a list of menuitems that make up the menu 
    private List menuItems;    
    
    private Long id;
	
    /**
     * 
     */
    public Menu() {
    	menuItems = new ArrayList();   
    	
    	menuItems.add(new MenuListItem(new MenuLink("Main ONe")));
    	MenuGroup mg;
    	MenuListItem mi ;
    	
        mg = new MenuGroup(new MenuLink("Main Two"));
        mi = new MenuListItem(new MenuLink("Sub one"));
        mg.add(mi);
        mi = new MenuListItem(new MenuLink("Sub two"));
        mg.add(mi);
        menuItems.add(mg);
        
        mg = new MenuGroup(new MenuLink("Main Three"));
        mg.add(mi);
        mi = new MenuListItem(new MenuLink("Sub one"));
        mg.add(mi);
        mi = new MenuListItem(new MenuLink("Sub two"));
        mg.add(mi);
        mi = new MenuListItem(new MenuLink("Sub three"));
        mg.add(mi);
        menuItems.add(mg);
        
        
    }
    
    public String draw() {
        StringBuffer sb = new StringBuffer();
        Iterator it;
        MenuItem menuItem;

        // create the container that the menu sits in
        sb.append("<div id=\"navcontainer\"><ul id=\"navlist\">");
        it = menuItems.iterator();
        
        while (it.hasNext()) {
            menuItem = (MenuItem) it.next();
            sb.append(menuItem.draw());
        }
        sb.append("</ul></div>");
        return sb.toString();
    }
    
    /**
     * @return Returns the menuItems.
     */
    public List getMenuItems() {
        return menuItems;
    }
    /**
     * @param menuItems The menuItems to set.
     */
    public void setMenuItems(List menuItems) {
        this.menuItems = menuItems;
    }
    /**
     * @return Returns the id.
     */
    public Long getId() {
        return id;
    }
    /**
     * @param id The id to set.
     */
    public void setId(Long id) {
        this.id = id;
    }
}
