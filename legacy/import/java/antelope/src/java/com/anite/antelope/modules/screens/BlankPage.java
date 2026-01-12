/*
 * Created on 03-Nov-2004
 */
package com.anite.antelope.modules.screens;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.modules.screens.BaseWorkflowScreen;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben.Gidley
 */
public class BlankPage extends BaseWorkflowScreen {

    /* (non-Javadoc)
     * @see com.anite.antelope.zebra.modules.screens.BaseWorkflowScreen#doBuildTemplate(org.apache.turbine.util.RunData, org.apache.velocity.context.Context, com.anite.antelope.zebra.om.AntelopeTaskInstance, com.anite.penguin.modules.tools.FormTool)
     */
    protected void doBuildTemplate(RunData runData, Context context, AntelopeTaskInstance taskInstance, FormTool tool) throws Exception {
        // Noop
        
    }

}
