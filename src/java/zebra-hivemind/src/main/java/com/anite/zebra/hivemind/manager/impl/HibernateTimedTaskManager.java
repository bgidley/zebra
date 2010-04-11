/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.manager.impl;

import java.util.List;

import org.hibernate.Criteria;
import org.hibernate.criterion.Restrictions;

import com.anite.zebra.hivemind.manager.TimedTaskManager;
import com.anite.zebra.hivemind.om.timedtask.Time;
import com.anite.zebra.hivemind.om.timedtask.TimedTask;

public class HibernateTimedTaskManager extends HibernateManager<TimedTask> implements TimedTaskManager {

    @SuppressWarnings("unchecked")
	public List<TimedTask> getTasksForTime(Time time) {

    	Criteria criteria = getSession().createCriteria(TimedTask.class);
    	criteria.add(Restrictions.eq("time", time));
    	
        return criteria.list();
    }
    
    

}
