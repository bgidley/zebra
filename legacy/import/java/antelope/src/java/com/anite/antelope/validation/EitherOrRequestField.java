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

package com.anite.antelope.validation;

import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

/**
 * Validates either field A or field B has been completed.
 * @author Ben.Gidley
 */
public class EitherOrRequestField extends AbstractBasePerFieldValidator {

    private static final String FIELDB = "fieldB";

    private static final String FIELDA = "fieldA";

    private String fieldB;

    private String fieldA;

    public void doCheckArguments() throws ReviewConfigurationException {
        fieldA = (String) this.args.get(FIELDA);
        fieldB = (String) this.args.get(FIELDB);

        if (fieldA == null) {
            throw new ReviewConfigurationException(
                    "Need to defined argument fieldA");
        }
        if (fieldB == null) {
            throw new ReviewConfigurationException(
                    "Need to defined argument fieldB");
        }
    }

    /* (non-Javadoc)
     * @see org.apache.turbine.component.review.main.api.Validator#validate(org.apache.turbine.util.parser.ParameterParser, java.lang.String, org.apache.turbine.component.review.util.ValidationResults)
     */
    public boolean doValidate(ParameterParser parameterParser, String key,
            ValidationResults validationResults)
            throws ReviewValidationException {

        String fieldAValue = parameterParser.getString(fieldA, "");
        String fieldBValue = parameterParser.getString(fieldB, "");

        if (fieldAValue.equals("") ^ fieldBValue.equals("")) {
            return true;
        }

        validationResults.addMessage(fieldA,
                "You must select exactly one of the next 2 fields");
        return false;
    }

}