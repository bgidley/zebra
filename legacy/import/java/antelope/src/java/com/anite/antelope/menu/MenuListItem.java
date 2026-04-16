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
 * @author <a href="mailTo:michael.jones@anite.com">Mike </a>
 */
public class MenuListItem extends MenuItem {

    protected MenuLink menuLink;

    /*
     * (non-Javadoc)
     * 
     * @see com.anite.antelope.modules.tools.MenuItem#draw()
     */
    public String draw() {
        StringBuffer sb = new StringBuffer();
        sb.append("<li ");
        buildParams(sb);
        sb.append(">");
        buildValue(sb);
        sb.append("</li>");
        return sb.toString();
    }

    /**
     * This method should be overridden by any subclass
     * wanting to provide a new value in the list item. This
     * is used for inserting another menu between the li links.
     * @param sb
     */
    protected void buildValue(StringBuffer sb) {
        sb.append(menuLink.draw());
    }

    /**
     * @return Returns the menuLink.
     */
    public MenuLink getMenuLink() {
        return menuLink;
    }

    /**
     * @param menuLink
     *            The menuLink to set.
     */
    public void setMenuLink(MenuLink menuLink) {
        this.menuLink = menuLink;
    }

    /**
     * @param menuLink
     */
    public MenuListItem(MenuLink menuLink) {
        super();
        this.menuLink = menuLink;
    }
}