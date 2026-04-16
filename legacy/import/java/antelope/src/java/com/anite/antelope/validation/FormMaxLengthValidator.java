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
import org.apache.turbine.component.review.validators.MaxLengthStringValidator;

import com.anite.penguin.formInformation.MaxLength;
import com.anite.penguin.formInformation.Size;

/**
 * Created 20-May-2004
 */
public class FormMaxLengthValidator extends MaxLengthStringValidator implements
        MaxLength, Size {

    private static final String MAXLENGTH = "maxlength";

    private String maxLength;

    /**
     * return the maxlength
     */
    public String getMaxLength() {

        return maxLength;
    }

    /**
     * Return the max length
     */
    public String getSize() {

        return maxLength;
    }

   /**
    * Check arguments and set max length string
    */
    public void checkArguments() throws ReviewConfigurationException {

        super.checkArguments();
        maxLength = args.get(MAXLENGTH).toString();
    }
}