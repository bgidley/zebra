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

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike </a>
 */
public class CaptionComparator extends TaskListComparator {
	/*
	 * (non-Javadoc)
	 * 
	 * @see java.util.Comparator#compare(java.lang.Object, java.lang.Object)
	 */
	public int compare(AntelopeTaskInstance ati0, AntelopeTaskInstance ati1) {
		if (getDirection().equals(ASCENDING)) {
			return ati1.getCaption().compareTo(ati0.getCaption());
		}
		return ati0.getCaption().compareTo(ati1.getCaption());
	}
}