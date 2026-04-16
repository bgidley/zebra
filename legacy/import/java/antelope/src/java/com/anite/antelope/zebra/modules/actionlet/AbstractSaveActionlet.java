/*
 * Created on 16-Nov-2004
 */
package com.anite.antelope.zebra.modules.actionlet;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben.Gidley
 */
public abstract class AbstractSaveActionlet extends AbstractActionlet implements SaveBeforeTriggerTransition{

    /** Ask each screenlet to save
     * By default just calls done 
     * */
    public boolean doPerformSave(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception {

        return doPerformDone(runData, context, taskInstance, processInstance, form);
    }
}
