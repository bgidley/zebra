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

package com.anite.zebra.hivemind.impl;

import java.util.List;

import org.hibernate.Query;
import org.hibernate.Session;
import org.hibernate.Transaction;

import com.anite.zebra.hivemind.om.state.Priority;
import com.anite.zebra.hivemind.util.RegistryHelper;

/**
 * A service to manager priorities
 * 
 * @author Ben.Gidley
 */
public class PriorityManager {

	public static final String LOW = "Low";

	public static final String URGENT = "Urgent";

	public static final String NORMAL = "Normal";

	private Long defaultPriorityId;
    
    private Session session;

    
    public Session getSession() {
        return session;
    }

    public void setSession(Session session) {
        this.session = session;
    }

    public void initializeService(){
        Query query = session.createQuery("from " + Priority.class.getName()
                + " where caption=:caption");

        // Find each value in the list
        query.setString("caption", LOW);
        List lowList = query.list();
        if (lowList.size() != 1) {
            Priority low = new Priority();
            low.setCaption(LOW);
            Transaction t = session.beginTransaction();
            session.save(low);
            t.commit();
        }

        query.setString("caption", NORMAL);
        List normalList = query.list();
        if (normalList.size() != 1) {
            Priority normal = new Priority();
            normal.setCaption(NORMAL);
            Transaction t = session.beginTransaction();
            session.save(normal);
            t.commit();
            this.defaultPriorityId = normal.getPriorityId();
        } else {
            Priority normal = (Priority) normalList.get(0);
            this.defaultPriorityId = normal.getPriorityId();
        }
            

        query.setString("caption", URGENT);
        List urgentList = query.list();
        if (urgentList.size() != 1) {
            Priority urgent = new Priority();
            urgent.setCaption(URGENT);
            Transaction t = session.beginTransaction();
            session.save(urgent);
            t.commit();
        }
    }

	/**
	 * Fetch the default priority
	 * 
	 * @return
	 */
	public Priority getDefaultPriority() {

		Session session = RegistryHelper.getInstance().getSession();

		return (Priority) session.load(Priority.class, this.defaultPriorityId);

	}

	public Long getDefaultPriorityId() {
		return this.defaultPriorityId;
	}
}