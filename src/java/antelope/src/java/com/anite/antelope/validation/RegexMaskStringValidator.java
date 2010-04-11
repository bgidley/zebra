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

import java.util.regex.Pattern;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

/**
 * Originally written by Peter Courcoux peter@courcoux.biz
 * 
 * A validator to check that a String input is in accordance with a regular
 * expression. Arguments required to be set in the Validation.xml file are as
 * follows. Please substitute values as appropriate. :- <argument
 * name="regexMask" type="string" value="mask" /> <argument
 * name="invalidFormatMessage" type="string" value="This item does not match
 * the expected format. Please re-enter." />
 */
public class RegexMaskStringValidator extends AbstractBasePerFieldValidator
{

    private static Log log = LogFactory.getLog(RegexMaskStringValidator.class);

    public void doCheckArguments() throws ReviewConfigurationException
    {

        String regexMask = (String) args.get("regexMask");
        String invalidFormatMessage = (String) args.get("invalidFormatMessage");
        if (regexMask == null) { throw new ReviewConfigurationException(
                "Unable to check String. regexMask argument missing."); }
        if (invalidFormatMessage == null) { throw new ReviewConfigurationException(
                "Unable to check String. invalidFormatMessage argument missing."); }

    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.fulcrum.validation.Validator#validate(org.apache.turbine.util.parser.ParameterParser,
     *      java.lang.String, java.util.Map,
     *      org.apache.fulcrum.validation.ValidationResultsMap)
     */
    public boolean doValidate(ParameterParser params, String key,
            ValidationResults validationData) throws ReviewValidationException
    {
        boolean valid = true;
        String[] values = params.getStrings(key);
        if (values == null) { return valid; }

        String regexMask = (String) args.get("regexMask");
        String invalidFormatMessage = (String) args.get("invalidFormatMessage");

        for (int i = 0; i < values.length; i++)
        {
            if (!Pattern.matches(regexMask, values[i]))
            {
                valid = false;
                validationData.addMessage(key, invalidFormatMessage);
            }
        }
        log.debug("Called validate() : returning :"
                + (new Boolean(valid)).toString());
        return valid;
    }

}