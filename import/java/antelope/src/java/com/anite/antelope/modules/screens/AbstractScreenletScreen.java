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
package com.anite.antelope.modules.screens;

import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.zebra.helper.ZebraHelper;
import com.anite.antelope.zebra.modules.screenlet.Screenlet;
import com.anite.antelope.zebra.modules.screens.BaseWorkflowScreen;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.penguin.modules.tools.FormTool;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * A screen that automatically runs screenlets
 * @author Ben.Gidley
 */
public abstract class AbstractScreenletScreen extends BaseWorkflowScreen {

    
    protected void doBuildTemplate(RunData runData, Context context,
            AntelopeTaskInstance taskInstance, FormTool form) throws Exception {

        buildPreScreenlets(runData, context, taskInstance, form);
        
        Screenlet[] screenlets = getScreenlets();
        for (int i =0; i < screenlets.length; i++){
            screenlets[i].doBuildTemplate(runData, context, taskInstance, form);
        }
        ITransaction t = ZebraHelper.getInstance().getStateFactory().beginTransaction();
        ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance);
        ZebraHelper.getInstance().getStateFactory().saveObject(taskInstance.getProcessInstance());
        t.commit();
    }
    
    public abstract Screenlet[] getScreenlets(); 

    public void buildPreScreenlets(RunData runData, Context context,
            AntelopeTaskInstance taskInstance, FormTool form) throws Exception{
        
    }
    
}
