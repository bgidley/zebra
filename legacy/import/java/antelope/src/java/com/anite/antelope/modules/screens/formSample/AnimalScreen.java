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
package com.anite.antelope.modules.screens.formSample;

import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.modules.actions.formSample.WhichAnimal;
import com.anite.antelope.om.Animal;

/**
 * @author Ben
 *  
 */
public class AnimalScreen extends VelocityScreen {

    public static final String AGE = "age";

    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {
        

        Animal animal = (Animal) data.getSession().getAttribute(
                WhichAnimal.ANIMAL);

        context.put("animal", animal);
    }

}