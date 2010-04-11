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

package com.anite.antelope.zebra.modules.actionlet;

import java.util.Iterator;
import java.util.Set;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * All concrete actionlets should extend this
 * @author Ben.Gidley
 */
public abstract class AbstractActionlet implements Actionlet {

    /** (non-Javadoc)
     *  Overide and Set to true to force taskInstance property set saving
     * @see com.anite.antelope.zebra.modules.actionlet.Actionlet#saveTaskInstancePropertySet()
     */
    public boolean saveTaskInstancePropertySet() {
        return false;
    }

    protected boolean isAllPrefixedFieldsValid(String prefix, FormTool form) {
        Set fields = form.getFields().getMultipleFields(prefix);
        for (Iterator iter = fields.iterator(); iter.hasNext();) {
            Field field = (Field) iter.next();
            if (!field.isValid()) {
                return false;
            }
        }
        return true;
    }

    /**
     * Called immediately prior to redirect to task list
     * Default do nothing
     * Overide if you want to do some work e.g. killing the task
     * You are not given Turbine stuff here to play with - because it 
     * will be a bad idea. So don't store them as class variables and play
     * with things 
     *
     */
    public void doCancel(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form) {
        // Noop
    }

    /**
     * Called before pause information has been saved and before redirecting 
     * to task list.
     * 
     * By default does nothing.
     * 
     * Can be used to change/modify information about to be paused.
     * Don't try and transition/kill workflows here - it will be messy.
     * Use do Cancel for that. 
     * 
     * You are not given Turbine stuff here to play with - because it 
     * will be a bad idea. So don't store them as class variables and play
     * with things 
     */
    public void doPause(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool from) {
        //Noop

    }
}