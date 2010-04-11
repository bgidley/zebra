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
package com.anite.antelope.session;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.entity.User;

/**
 * Find a user for the current request via the magic of threadlocals
 * @author Ben.Gidley
 */
public class UserLocator {
    private static final Log log = LogFactory.getLog(UserLocator.class);
    
    private static ThreadLocal threadLocal;
    
    static {
        if (threadLocal == null){
            threadLocal = new ThreadLocal();
        }
    }
    
    public static void setLoggedInUser(User user){               
        threadLocal.set(user);
    }
    
    /**
     * Gets the logged in user or null if there is not one set
     * @return
     */
    public static User getLoggedInUser(){
        return (User) threadLocal.get();
    }
}
