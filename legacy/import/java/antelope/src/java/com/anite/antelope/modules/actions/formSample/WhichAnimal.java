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

import com.anite.antelope.managers.AnimalManager;
import com.anite.antelope.om.Animal;
import com.anite.antelope.om.Llama;
import com.anite.antelope.om.Moorhen;
import com.anite.meercat.PersistenceLocator;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * @author Ben Gidley
 *  
 */
public class WhichAnimal extends VelocityAction {

    public static final String ANIMAL = "com.anite.antelope.modules.actions.formSample.WhichAnimal.Animal";

    /**
     * Process the select form
     */
    public void doPerform(RunData data, Context context) throws Exception {
        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        if (form.isAllValid()) {
            // Passed all validation
            Field type = (Field) form.getFields().get("animaltype");
            AnimalManager manager = new AnimalManager();
            Animal animal = manager.createAnimal(type.getValue());
            animal.setOwnerLoginName(data.getUser().getName());

            Field name = (Field) form.getFields().get("name");
            animal.setName(name.getValue());

            Session session = PersistenceLocator.getInstance()
                    .getCurrentSession();
            Transaction t = session.beginTransaction();
            session.save(animal);
            t.commit();

            // Go to success URL
            if (animal instanceof Llama) {
                data.setScreenTemplate("formSample,CongratulationsLlama.vm");
            } else if (animal instanceof Moorhen) {
                data.setScreenTemplate("formSample,CongratulationsMoorhen.vm");
            }
            // Reinitialse form tool for new screen
            form.reinitialiseForScreenEndpoint();

            data.getSession().setAttribute(ANIMAL, animal);
        } else {
            // Failed some validation

            // Return to previous screen
            data.setScreenTemplate("formSample,WhichAnimal.vm");
        }
    }
}