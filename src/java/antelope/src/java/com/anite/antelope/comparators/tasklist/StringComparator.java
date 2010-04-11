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

import com.anite.antelope.zebra.om.AntelopeTaskInstance;

/**
 * Compares 2 strings - null safe
 * @author Ben.Gidley
 */
public abstract class StringComparator extends TaskListComparator {

    public int compare(AntelopeTaskInstance task0, AntelopeTaskInstance task1) {
        String text0 = task0.getCaption();
        String text1 = task1.getCaption();

        if (text0 == null && text1 == null) {
            // both are null so can't call compareTo
            return 0;
        } else if (text0 == null) {
            if (getDirection().equals(ASCENDING)) {
                return -1;
            }
            return 1;

        } else if (text1 == null) {
            if (getDirection().equals(ASCENDING)) {
                return 1;
            }
            return -1;

        }

        if (getDirection().equals(ASCENDING)) {
            return text1.compareTo(text0);
        }
        return text0.compareTo(text1);
    }

    public abstract String getField(AntelopeTaskInstance task);

}