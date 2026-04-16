/*
 * Copyright 2005 Anite - Central Government Division
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

import java.util.StringTokenizer;

import org.apache.commons.lang.StringUtils;
import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.component.review.validators.AbstractValidator;
import org.apache.turbine.util.parser.ParameterParser;

/**
 * @author Mark Andrews
 * 
 * Fails validation if the named fields are all null / empty string You can optionally
 * specify "isNullMessage" to provide a custom message other than the default
 * "At least one field must have content."
 *  
 */
public class NotAllNullValidator extends AbstractValidator {

    /**
     * constant for "At least one field must have content."
     */
    private static final String MESSAGE_FAIL = "At least one field must have content.";

    /**
     * constant for "isNullMessage"
     */
    private static final String PARAM_ISNULLMESSAGE = "isNullMessage";

    /**
     * constant for "keys"
     */
    private static final String PARAM_ALTKEY = "keys";

    /**
     * {@inheritDoc}
     */
    public final void checkArguments() throws ReviewConfigurationException {

        //If we have no keys then not much point in running
        if (!args.containsKey(PARAM_ALTKEY)) {
            throw new ReviewConfigurationException("No " + PARAM_ALTKEY
                    + " argument for not all null validator");
        }
        if (StringUtils.isEmpty((String) args.get(PARAM_ALTKEY))) {
            throw new ReviewConfigurationException(PARAM_ALTKEY
                    + " argument for not all null validator is empty");
        }

        //If we don't have a message not much point in running as will tell
        // user nothing
        if (args.containsKey(PARAM_ISNULLMESSAGE)) {
            if (StringUtils.isEmpty((String) args.get(PARAM_ISNULLMESSAGE))) {
                throw new ReviewConfigurationException(PARAM_ISNULLMESSAGE
                        + " argument for not all null validator is empty");
            }
        }
    }

    /**
     * {@inheritDoc}
     */
    public final boolean validate(ParameterParser params, String key,
            ValidationResults validationData) {
        String keyToCheck = key;
        if (args.containsKey(PARAM_ALTKEY)) {
            keyToCheck = args.get(PARAM_ALTKEY).toString();
        }

        StringTokenizer st = new StringTokenizer(keyToCheck, ";");

        boolean failed = true;
        String notNull = null;
        while (st.hasMoreTokens()) {
            String theKey = st.nextToken().trim();

            if (validationData.getValue(theKey) != null && validationData.getValue(theKey).toString().length() > 0) {
                failed = false;
            } 
            else{
                notNull = theKey;
            }
        } 

        if (failed) {
            if (args.containsKey(PARAM_ISNULLMESSAGE)) {
                validationData.addMessage(notNull, args.get(
                        PARAM_ISNULLMESSAGE).toString());
            } else {
                validationData.addMessage(notNull, MESSAGE_FAIL);
            }
        }


        return !failed;
    }
}