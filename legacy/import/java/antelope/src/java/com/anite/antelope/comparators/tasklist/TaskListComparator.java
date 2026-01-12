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

import java.util.Comparator;

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 *
 * @author <a href="mailTo:michael.jones@anite.com">Mike</a>
 */
public abstract class TaskListComparator implements Comparator {

	public final static String ASCENDING = "ascending";
	public final static String DESCENDING = "descending";
	
	private String direction = DESCENDING;

	public String getDirection() {
		return direction;
	}
	public void setDirection(String direction) {
		this.direction = direction;
	}
	
	public int compare(Object task1, Object task2){
		return compare((AntelopeTaskInstance)task1, (AntelopeTaskInstance)task2);
	}

	/* (non-Javadoc)
	 * @see java.util.Comparator#compare(java.lang.Object, java.lang.Object)
	 */
	public abstract int compare(AntelopeTaskInstance ati0, AntelopeTaskInstance ati1) ;

}
