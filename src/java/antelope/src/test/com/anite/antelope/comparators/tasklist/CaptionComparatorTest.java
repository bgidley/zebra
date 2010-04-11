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
import java.util.Collections;
import java.util.List;

import junit.framework.TestCase;

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Mike </a>
 */
public class CaptionComparatorTest extends TestCase {

	private List taskList = new ArrayList();

	private TaskListComparator captionComparator;

	private AntelopeTaskInstance atiA, atiB, atiC;

	public void setUp() {
		//AntelopeTaskInstance ati0;
		//AntelopeTaskInstance ati1;
		captionComparator = new CaptionComparator();
		atiA = new AntelopeTaskInstance();
		atiA.setCaption("aaa");
		taskList.add(atiA);
		atiB = new AntelopeTaskInstance();
		atiB.setCaption("bbb");
		taskList.add(atiB);
		atiC = new AntelopeTaskInstance();
		atiC.setCaption("ccc");
		taskList.add(atiC);
	}

	public void testAscedingCompare() {
		captionComparator.setDirection(CaptionComparator.ASCENDING);
		Collections.sort(taskList, captionComparator);

		assertTrue(taskList.get(2) == atiA);
		assertTrue(taskList.get(1) == atiB);
		assertTrue(taskList.get(0) == atiC);
	}

	public void testDescedingCompare() {
		captionComparator.setDirection(CaptionComparator.DESCENDING);
		Collections.sort(taskList, captionComparator);
		assertTrue(taskList.get(0) == atiA);
		assertTrue(taskList.get(1) == atiB);
		assertTrue(taskList.get(2) == atiC);
	}
}