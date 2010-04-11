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

package com.anite.antelope.modules.actions.formSample;

import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import org.apache.turbine.modules.actions.VelocityAction;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.screens.formSample.AnimalScreen;
import com.anite.antelope.om.Animal;
import com.anite.meercat.PersistenceLocator;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben
 *  
 */
public class UpdateAnimalAction extends VelocityAction {

    /**
     * Save the updated animal fields
     */
    public void doPerform(RunData data, Context context) throws Exception {

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            // Passed all validation
            String age = ((Field) form.getFields().get(AnimalScreen.AGE))
                    .getValue().toString();
            Animal animal = (Animal) data.getSession().getAttribute(
                    WhichAnimal.ANIMAL);
            animal.setAge(Integer.parseInt(age));

            Session session = PersistenceLocator.getInstance()
                    .getCurrentSession();
            Transaction t = session.beginTransaction();
            session.saveOrUpdate(animal);
            t.commit();

            // Go to success URL
            data.setScreenTemplate("formSample,TheMenagerie.vm");
        } else {
            // Failed some validation

            // Return to previous screen the previous screen must have set
            // itself as setPage

        }
    }
}