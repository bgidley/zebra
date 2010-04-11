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
import org.apache.turbine.component.review.validators.AbstractValidator;
import org.apache.turbine.util.parser.ParameterParser;

/**
 * @author Ben.Gidley
 */
public abstract class AbstractBasePerFieldValidator extends AbstractValidator {

    public static final String FIELD = "field";

    private String field = null;

    /* (non-Javadoc)
     * @see org.apache.turbine.component.review.main.api.Validator#checkArguments()
     */
    public final void checkArguments() throws ReviewConfigurationException {
        if (args.containsKey(FIELD)) {
            field = (String) args.get(FIELD);
        }
        doCheckArguments();
    }

    public abstract void doCheckArguments() throws ReviewConfigurationException;

    /* (non-Javadoc)
     * @see org.apache.turbine.component.review.main.api.Validator#validate(org.apache.turbine.util.parser.ParameterParser, java.lang.String, org.apache.turbine.component.review.util.ValidationResults)
     */
    public final boolean validate(ParameterParser params, String key,
            ValidationResults validationData) throws ReviewValidationException {
        if (field != null) {
            return doValidate(params, field, validationData);
        }
        return doValidate(params, key, validationData);

    }

    public abstract boolean doValidate(ParameterParser params, String key,
            ValidationResults validationData);
}