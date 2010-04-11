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

package com.anite.antelope.comparators.tasklist;

import java.util.Date;

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 * @author Ben.Gidley
 */
public abstract class DateComparator extends TaskListComparator {

    /**
     * Sort dates in a null safe manner. Calls down to implementing call
     * to locate field
     */
    public int compare(AntelopeTaskInstance ati0, AntelopeTaskInstance ati1) {
        Date date0 = getDateField(ati0);
        Date date1 = getDateField(ati1);

        if (date0 == null && date1 == null) {
            // both are null so can't call compareTo
            return 0;
        } else if (date0 == null) {
            if (getDirection().equals(ASCENDING)) {
                return -1;
            }
            return 1;
        } else if (date1 == null) {
            if (getDirection().equals(ASCENDING)) {
                return 1;
            }
            return -1;
        }

        if (getDirection().equals(ASCENDING)) {
            return date1.compareTo(date0);
        }
        return date0.compareTo(date1);
    }

    /**
     * Return the date to be sorted
     */
    public abstract Date getDateField(AntelopeTaskInstance task);
}