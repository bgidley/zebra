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
public interface SaveBeforeTriggerTransition {
    /**
     * Call when anything that saves is pressed     
     * @param runData
     * @param context
     * @param taskInstance
     * @param processInstance
     * @param tool
     * @return true/false - if any actionlet returns false we do not transition
     * @throws Exception
     */
    public boolean doPerformSave(RunData runData, Context context,
            AntelopeTaskInstance taskInstance,
            AntelopeProcessInstance processInstance, FormTool form)
            throws Exception;
}
