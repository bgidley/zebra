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

package com.anite.antelope.zebra.managers;

import java.util.List;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.zebra.om.Priority;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;

/**
 * Represents a singleton.
 * @author Ben.Gidley
 */
public class PriorityManager {

    /**
     * Holds singleton instance
     */
    private static PriorityManager instance;
    public static final String LOW = "Low";
    public static final String URGENT = "Urgent";
    public static final String NORMAL = "Normal";

    private final static Log log = LogFactory.getLog(PriorityManager.class);
    
    private Long defaultPriorityId;
    
    
    /**
     * prevents instantiation
     */
    private PriorityManager() {
        // prevent creation
        
        try {
            Session session = PersistenceLocator.getInstance().getCurrentSession();
            List priorityList = session.find("from " + Priority.class.getName() + " as p where p.caption = '" + NORMAL +"'" );
            Priority defaultPriority = (Priority) priorityList.get(0);
            defaultPriorityId = defaultPriority.getPriorityId();            
        } catch (PersistenceException e) {
            log.error("Trying to find priority failed", e);
            throw new RuntimeException(e);
        } catch (HibernateException e) {
            log.error("Trying to find priority failed", e);
            throw new RuntimeException(e);
        }
    }

    /**
     * Returns the singleton instance.
     * @return	the singleton instance
     */
    static public PriorityManager getInstance() {
        if (instance == null) {
            instance = new PriorityManager();
        }
        return instance;
    }

    /**
     * Fetch the default priority
     * @return
     */
    public Priority getDefaultPriority() {
        try {
            Session session = PersistenceLocator.getInstance().getCurrentSession();
            return (Priority) session.load(Priority.class, this.defaultPriorityId);
        } catch (PersistenceException e) {
            log.error("Trying to find priority failed", e);
            throw new RuntimeException(e);
        } catch (HibernateException e) {
            log.error("Trying to find priority failed", e);
            throw new RuntimeException(e);
        }
        
    }
    
    public Long getDefaultPriorityId(){
        return defaultPriorityId;
    }
}