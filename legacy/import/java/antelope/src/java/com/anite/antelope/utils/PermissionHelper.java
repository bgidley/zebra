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

package com.anite.antelope.utils;

import java.util.Iterator;

import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Group;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.Role;
import org.apache.fulcrum.security.entity.SecurityEntity;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.GroupSet;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.RoleSet;
import org.apache.fulcrum.security.util.SecuritySet;

/**
 * @author Michael.Jones
 */
public class PermissionHelper {

    private PermissionHelper() {

    }

    /**
     * This method accepts a username and permission as a string and reutrn a
     * boolean showing whether or not the user has the specific permission.
     * 
     * @param userName
     * @param permission
     * @return @throws
     *         Exception
     */
    public static boolean hasUserPermission(String userName, String permission)
            throws Exception {
        SecurityService securityService;
        UserManager usermanager;
        User user;
        DynamicAccessControlList dacl;

        securityService = AvalonServiceHelper.instance().getSecurityService();
        usermanager = securityService.getUserManager();
        user = usermanager.getUser(userName);
        dacl = (DynamicAccessControlList) usermanager.getACL(user);

        return dacl.hasPermission(permission);
    }

    /**
     * This method returns the values from <code>userGroups</code> that do not
     * appear in <code>allGroups</code>. The function acts like
     * <code>userGroups</code> XOR <code>userGroups</code>. is all the
     * groups
     * 
     * @param userGroups
     * @param allGroups
     * @return
     */
    public static GroupSet groupSetXOR(GroupSet userGroups, GroupSet allGroups) {
        return (GroupSet) securitySetXOR(userGroups, allGroups);
    }

    /**
     * This method returns the values from <code>userGroups</code> that do not
     * appear in <code>allGroups</code>. The function acts like
     * <code>userGroups</code> XOR <code>userGroups</code>. is all the
     * groups
     * 
     * @param groupRoles
     * @param allRoles
     * @return
     */
    public static RoleSet roleSetXOR(RoleSet groupRoles, RoleSet allRoles) {
        return (RoleSet) securitySetXOR(groupRoles, allRoles);
    }

    /**
     * This method returns the values from <code>userGroups</code> that do not
     * appear in <code>allGroups</code>. The function acts like
     * <code>userGroups</code> XOR <code>userGroups</code>. is all the
     * groups
     * 
     * @param rolePermssions
     * @param allPermissions
     * @return
     */
    public static PermissionSet permissionSetXOR(PermissionSet rolePermssions,
            PermissionSet allPermissions) {
        return (PermissionSet) securitySetXOR(rolePermssions, allPermissions);
    }

    /**
     * This method returns the values from <code>ss1</code> that do not appear
     * in <code>ss2</code>.
     * 
     * @param userGroups
     * @param allGroups
     * @return
     */

    private static SecuritySet securitySetXOR(SecuritySet ss1, SecuritySet ss2) {
        SecuritySet ss;
        boolean shouldAdd;
        Iterator ss1It;
        Iterator ss2It;
        SecurityEntity e1, e2;
        Class c;

        try {
            c = Class.forName(ss1.getClass().getName());
            ss = (SecuritySet) c.newInstance();

            //          get the iterator for the groups
            ss2It = ss2.iterator();

            // loop round allGroups and add the ones that arent
            // in the user group
            while (ss2It.hasNext()) {
                e1 = (SecurityEntity) ss2It.next();
                shouldAdd = true;

                // need to get the iterator here so that its new
                // for each group
                ss1It = ss1.iterator();
                while (ss1It.hasNext()) {
                    e2 = (SecurityEntity) ss1It.next();
                    if (e1.getId() == e2.getId()) {
                        shouldAdd = false;
                        break; // come out of the while
                    }
                }
                // if the group wasnt in the user group add it
                // this is due to a bug in fulcrm that the security set
                // should have an abstract add method. there is a method
                // but it is not abstract and it throws a runtime exception
                if (shouldAdd) {
                    if (ss instanceof GroupSet) {
                        ((GroupSet) ss).add((Group) e1);
                    }
                    if (ss instanceof RoleSet) {
                        ((RoleSet) ss).add((Role) e1);
                    }
                    if (ss instanceof PermissionSet) {
                        ((PermissionSet) ss).add((Permission) e1);
                    }
                }
            }

        } catch (Exception e) {
            throw new RuntimeException(e.getLocalizedMessage());
        }

        return ss;
    }
}