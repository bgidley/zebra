/*
 * Created on 13-Sep-2004
 */
package com.anite.antelope.zebra.modules.actions;

import java.util.Iterator;
import java.util.Set;

import org.apache.commons.lang.StringUtils;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.modules.actionlet.Actionlet;
import com.anite.antelope.zebra.modules.actionlet.SaveBeforeTriggerTransition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben.Gidley
 */
public abstract class ActionletWorkflowAction extends BaseWorkflowAction {

    /**
     * Process All this Actions Actionlets  
     */
    protected boolean doPerform(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception {

        Actionlet[] actionlets = getActionLets();

        boolean returnValue = false;
        if (!(form.getField(DONE_NAME).getValue().equals(""))) {
            returnValue = true;
            taskInstance.setRoutingAnswer(getDefaultDoneRoutingAnswer());
            for (int i = 0; i < actionlets.length; i++) {
                if (!actionlets[i].doPerformDone(runData, context,
                        taskInstance, processInstance, form)) {
                    returnValue = false;
                }
            }
        } else {
            boolean saveTaskInstance = false;
            // find if any of the triggers has been called for the actionlets
            for (int i = 0; i < actionlets.length; i++) {
                if (actionlets[i] == null) {
                    continue;
                }
                boolean interested = false;
                String[] triggers = actionlets[i].getTriggerFieldNames();
                if (triggers != null && triggers.length != 0) {

                    triggersLoop: for (int j = 0; j < triggers.length; j++) {
                        // check if any of this actionlets triggers have been called 
                        if (containsActiveTrigger(form, triggers[j])) {
                            interested = true;
                            break triggersLoop;
                        }
                    }
                    if (interested) {// do the trigger
                        returnValue = actionlets[i].doPerformTrigger(runData,
                                context, taskInstance, processInstance, form);
                        saveTaskInstance = actionlets[i]
                                .saveTaskInstancePropertySet();
                    }
                }
            }
            if (saveTaskInstance) {
                this.saveTaskInstancePropertySet(taskInstance, form);
            }
            if (returnValue) {
                for (int i = 0; i < actionlets.length; i++) {
                    if (actionlets[i] instanceof SaveBeforeTriggerTransition) {
                        ((SaveBeforeTriggerTransition) actionlets[i])
                                .doPerformSave(runData, context, taskInstance,
                                        processInstance, form);
                    }
                }
            }
        }
        return returnValue;
    }

    /**
     * @param form
     * @param triggers
     * @param j
     * @return
     */
    protected boolean containsActiveTrigger(FormTool form, String trigger) {
        // pessimistic - it will never work :(
        boolean containsActiveTrigger = false;
        Set keys = form.getFields().keySet();

        fieldLoop: for (Iterator iter = keys.iterator(); iter.hasNext();) {
            String key = (String) iter.next();
            if (key.equals(trigger)) { // the tigger is there as a normal field                
                if (!StringUtils.isEmpty(form.getField(key).getValue())) {
                    containsActiveTrigger = true;
                    break fieldLoop; // try to be as quick as possible
                }

            } else { // check if its part of a multi field thing
                Field field = (Field) form.getFields().get(key);
                if (field.getNameWithoutSuffix().equals(trigger)) {
                    if (!StringUtils.isEmpty(form.getField(key).getValue())) {
                        containsActiveTrigger = true;
                        break fieldLoop; // try to be as quick as possible
                    }
                }
            }
        }
        return containsActiveTrigger;
    }

    private boolean triggered(Field field) {
        return !StringUtils.isEmpty(field.getValue());
    }

    /* (non-Javadoc)
     * @see com.anite.antelope.zebra.modules.actions.BaseWorkflowAction#enforceValidation()
     */
    protected boolean enforceValidation() {
        return false;
    }

    /**
     * Return an array of actionlets for this page
     * @return
     */
    public abstract Actionlet[] getActionLets();

    /**
     * The default routing name to follow when Done is pressed
     * Any action can change this by calling
     * taskInstance.setRoutingAnswer("Their rotuing Name");
     * @return
     */
    public String getDefaultDoneRoutingAnswer() {
        return "";
    }

    /**
     * Simply calls down to each actionlet in turn 
     */
    protected void doCancel(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form) {

        Actionlet[] actionlets = getActionLets();
        for (int i = 0; i < actionlets.length; i++) {
            actionlets[i].doCancel(taskInstance, processInstance, form);
        }
    }

    /**
     * Simply calls down to each actionlet in turn
     */
    protected void doPause(AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form) {

        Actionlet[] actionlets = getActionLets();
        for (int i = 0; i < actionlets.length; i++) {
            actionlets[i].doPause(taskInstance, processInstance, form);
        }

    }
}