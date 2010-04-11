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
package com.anite.antelope.comparators.tasklist;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Date;
import java.util.List;

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

import junit.framework.TestCase;

/**
 *
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 */
public class DateCreatedComparatorTest extends TestCase {
	private List taskList = new ArrayList();

	private TaskListComparator comparator;

	private AntelopeTaskInstance atiNow, ati1990, ati2090;

	public void setUp() {
		//AntelopeTaskInstance ati0;
		//AntelopeTaskInstance ati1;
		comparator = new DateCreatedComparator();
		
		Calendar calendar = Calendar.getInstance();
		
		atiNow = new AntelopeTaskInstance();
		atiNow.setDateCreated(new Date(calendar.getTimeInMillis()));
		taskList.add(atiNow);
		
		calendar.set(Calendar.YEAR, 1990);
		ati1990 = new AntelopeTaskInstance();
		ati1990.setDateCreated(new Date(calendar.getTimeInMillis()));
		taskList.add(ati1990);
		
		calendar.set(Calendar.YEAR, 2090);
		ati2090 = new AntelopeTaskInstance();
		ati2090.setDateCreated(new Date(calendar.getTimeInMillis()));
		taskList.add(ati2090);
	}
	
	public void testAscedingCompare() {
		comparator.setDirection(TaskListComparator.ASCENDING);
	
		Collections.sort(taskList, comparator);
		assertTrue(taskList.get(0) == ati2090);
		assertTrue(taskList.get(1) == atiNow);
		assertTrue(taskList.get(2) == ati1990);		
	}

	public void testDescedingCompare() {
		comparator.setDirection(TaskListComparator.DESCENDING);
		Collections.sort(taskList, comparator);
		
		assertTrue(taskList.get(0) == ati1990);
		assertTrue(taskList.get(1) == atiNow);
		assertTrue(taskList.get(2) == ati2090);	
		
	}

}
