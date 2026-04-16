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

package com.anite.antelope.validation;

import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

import com.anite.penguin.form.Option;
import com.anite.penguin.formInformation.Options;

/**
 * This validator tests a select list value is from a comma seperated list of
 * values. If also prefills the options with the possible values. It assumes the
 * caption is the same as the value Created 20-May-2004
 */
public class SelectList extends AbstractBasePerFieldValidator implements Options {

    private static final String VALUES = "values";

    private String[] values;

    /**
     * Load the csv seperated values
     */
    public void doCheckArguments() throws ReviewConfigurationException {
        try {
            String valuesCombined = (String) args.get(VALUES);

            values = valuesCombined.split(",");
        } catch (RuntimeException e) {
            throw new ReviewConfigurationException("Unable to split values", e);
        }

    }

   /**
    * Simply check is item is in list
    */
    public boolean doValidate(ParameterParser parameterPaser, String key,
            ValidationResults validationData) throws ReviewValidationException {
        
        String[] currentValues = parameterPaser.getStrings(key);
        
        for (int i = 0; i < currentValues.length; i++){
            boolean valid = false;
            for(int j =0; j < values.length; j++){
                if (currentValues[i].equals(values[j])){
                    valid = true;
                }
            }
            if (!valid){
                validationData.addMessage(key, "Item not in allowed list");
                return false;
            }
        }        
        return true;
    }

    /**
     * (non-Javadoc)
     * 
     * @see com.anite.penguin.formInformation.Options#getOptions()
     */
    public Option[] getOptions() {
       Option[] options = new Option[values.length];
       
       for (int i=0; i < values.length; i++){
           options[i] = new Option();
           options[i].setCaption(values[i]);
           options[i].setValue(values[i]);
       }       
       return options;
    }

}