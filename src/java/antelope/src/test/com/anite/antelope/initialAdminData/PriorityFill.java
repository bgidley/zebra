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

package com.anite.antelope.initialAdminData;

import junit.framework.TestCase;
import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import com.anite.antelope.zebra.managers.PriorityManager;
import com.anite.antelope.zebra.om.Priority;
import com.anite.meercat.PersistenceLocator;

/**
 * @author Ben.Gidley
 */
public class PriorityFill extends TestCase {
    public void testFillPriority() throws Exception{
        Session session = PersistenceLocator.getInstance().getCurrentSession();
        
        Transaction t = session.beginTransaction();
        
        Priority priority = new Priority();
        priority.setCaption(PriorityManager.URGENT);
        priority.setSortKey(new Integer(100));
        session.saveOrUpdate(priority);
        priority = new Priority();
        priority.setCaption(PriorityManager.NORMAL);
        priority.setSortKey(new Integer(50));
        session.saveOrUpdate(priority);
        priority = new Priority();
        priority.setCaption(PriorityManager.LOW);
        priority.setSortKey(new Integer(10));
        session.saveOrUpdate(priority);
        t.commit();
       
        
    }
}
