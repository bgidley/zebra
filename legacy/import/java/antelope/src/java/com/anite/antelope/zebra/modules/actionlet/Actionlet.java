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

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * represents an action for a part of a screen
 * @author Ben.Gidley
 */
public interface Actionlet {
    
    /**
     * Child classes implement this to validate and provide business
     * logic.
     * If true returned from any actionlet we will attempt to transition the workflow
     * 
     * @param runData
     * @param context
     * @param taskInstance
     * @param tool
     * @return true if we should transition
     * @throws Exception
     */
    public boolean doPerformTrigger(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception;
    
    /**
     * Call when the final Done button is pressed
     * @param runData
     * @param context
     * @param taskInstance
     * @param processInstance
     * @param tool
     * @return true/false - if any actionlet returns false we do not transition
     * @throws Exception
     */
    public boolean doPerformDone(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception;
    
    /**
     * Trigger field names
     * Return a string[] of fields which if set the doPerform bit
     * of this actionlet is to be called
     * 
     * If 2 actionlets want a button then something pretty
     * random will happen
     * 
     * So keep button names unique! 
     */
    public String[] getTriggerFieldNames();
    
    /**
     * Return true if you want the workflow to save the task instnace property set into the process property set.
     * It will be keyed on the TaskDefinitionID and loaded when any taskInstance with that defintion Id is shown
     * @return
     */
    public boolean saveTaskInstancePropertySet();
    
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
     * 
     * @param taskInstance
     * @param processInstance
     * @param tool
     */
    public void doPause(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form);
    
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
            AntelopeProcessInstance processInstance, FormTool form);
    
        
}
