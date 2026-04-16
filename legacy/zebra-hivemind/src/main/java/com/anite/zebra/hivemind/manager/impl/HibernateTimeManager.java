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

import org.hibernate.Criteria;
import org.hibernate.criterion.Restrictions;

import com.anite.zebra.hivemind.manager.TimeManager;
import com.anite.zebra.hivemind.om.timedtask.Time;

public class HibernateTimeManager extends HibernateManager<Time> implements TimeManager{

	public Time createOrFetchTime(int hours, int mins) {
		Criteria criteria = getSession().createCriteria(Time.class);
		criteria.add(Restrictions.eq("hour", hours));
		criteria.add(Restrictions.eq("minute", mins));
		
		Time result = (Time) criteria.uniqueResult();
		
		if (result == null){
			result = new Time();
			result.setHour(hours);
			result.setMinute(mins);
			this.saveOrUpdate(result);
		}
		
		return result;
	}

}
