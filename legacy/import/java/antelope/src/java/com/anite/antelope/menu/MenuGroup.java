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

/**
 * The class extends the menuItem class and adds the ability to have children.
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 *  
 */
public class MenuGroup extends MenuListItem {

    /**
     * This is used to tell if the menu has been opened so you can see the
     * children.
     */
    private boolean open = true;

    /**
     * A list of the menuItems for the group
     */
    private List menuItems;

    /**
     *  
     */
    public MenuGroup(MenuLink link) {
        super(link);
        htmlClass = "subNavList";
        menuItems = new ArrayList();
    }

    /**
     * Ok this now produces the div that will contain all the menu items that
     * are contained in the list
     * 
     * FIXME should this really have he divs all inside togther or should they
     * be seperated out? also what if javascript it turned off, this really
     * should display them all. Or should it?
     *  
     */
    protected void buildValue(StringBuffer sb) {
        // TODO need to put some stuff in here to tell the action or javascript
        // to open or close
        sb.append(menuLink.draw());
        if (open) {
            Iterator it;
            MenuItem menuItem;
            it = menuItems.iterator();

            sb.append("<ul ");
            buildParams(sb);
            sb.append(">");
            while (it.hasNext()) {
                menuItem = (MenuItem) it.next();
                sb.append(menuItem.draw());
            }
            sb.append("</ul>");
        }
    }

    /**
     * Add a new menuItem to the group
     * 
     * @param menuItem
     */
    public void add(MenuItem menuItem) {
        menuItems.add(menuItem);
    }

    /**
     * @return Returns the menuItems.
     */
    public List getMenuItems() {
        return menuItems;
    }

    /**
     * @param menuItems
     *            The menuItems to set.
     */
    public void setMenuItems(List menuItems) {
        this.menuItems = menuItems;
    }

    /**
     * @return Returns the isOpen.
     */
    public boolean isOpen() {
        return open;
    }

    /**
     * @param isOpen
     *            The isOpen to set.
     */
    public void setOpen(boolean isOpen) {
        this.open = isOpen;
    }

}