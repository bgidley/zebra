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

public class AntelopeConstants {

    // ############################################################
    // A list of the names of the groups should go here
    // ############################################################
    public static final String GROUP_ADMIN = "GROUP_ADMIN";

    public static final String GROUP_BASIC = "GROUP_BASIC";

    // ############################################################
    // A list of the names of the roles should go here
    // ############################################################
    public static final String ROLE_USER_ADMIN = "ROLE_USER_ADMIN";

    public static final String ROLE_USER_BASIC = "ROLE_USER_BASIC";

    // ############################################################
    // A list of the names of the permissions should go here
    // ############################################################
    public static final String PERMISSION_CHANGE_PASSWORD = "PERMISSION_CHANGE_PASSWORD";

    public static final String PERMISSION_ADD_USER = "PERMISSION_ADD_USER";

    public static final String PERMISSION_EDIT_PERMISSIONS = "PERMISSION_EDIT_PERMISSIONS";
    
    public static final String PERMISSION_SYSTEM_ACCESS = "systemAccess";
    
    public static final String KILL_TASK_PERMISSION = "killtask";

    /**
     * Hahaha you cant instantiate this class it only contains constants for
     * Antelope. None of this silly implementing interfaces full of constants
     * here.
     *  
     */
    private AntelopeConstants() {
    }
}