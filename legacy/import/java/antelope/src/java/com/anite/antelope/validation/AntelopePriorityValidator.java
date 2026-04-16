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

import java.util.List;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

import com.anite.antelope.zebra.om.Priority;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;
import com.anite.penguin.form.Option;
import com.anite.penguin.formInformation.Options;

/**
 * A validator designed to supply priorities to a Task
 * Null is not an option
 * @author Ben Gidley
 */
public class AntelopePriorityValidator extends AbstractBasePerFieldValidator implements
        Options {

    private static final String PLEASE_PICK_A_VALID_PRIORITY = "Please pick a valid priority";

    private final static Log log = LogFactory
            .getLog(AntelopePriorityValidator.class);

    private static Option[] options = null;

    public Option[] getOptions() {
        return options;
    }

    /* (non-Javadoc)
     * @see org.apache.turbine.component.review.validators.AbstractValidator#checkArguments()
     */
    public void doCheckArguments() throws ReviewConfigurationException {
        if (options == null) {
            try {
                Session session = PersistenceLocator.getInstance()
                        .getCurrentSession();
                List priorities = session
                        .find("from Priority p order by p.sortKey");

                options = new Option[priorities.size()];
                for (int i = 0; i < options.length; i++) {
                    Priority priority = (Priority) priorities.get(i);
                    Option option = new Option();
                    option.setCaption(priority.getCaption());
                    option.setValue(priority.getPriorityId().toString());
                    options[i] = option;
                }
            } catch (PersistenceException e) {
                log.error(e);
                throw new ReviewConfigurationException(
                        "Trying to load priority couldn't find database");
            } catch (HibernateException e) {
                log.error(e);
                throw new ReviewConfigurationException(
                        "Trying to load priority couldn't find database");
            }
        }
    }

    /* (non-Javadoc)
     * @see org.apache.turbine.component.review.validators.AbstractValidator#validate(org.apache.turbine.util.parser.ParameterParser, java.lang.String, org.apache.turbine.component.review.util.ValidationResults)
     */
    public boolean doValidate(ParameterParser parameterParser, String key,
            ValidationResults validationResults)
            throws ReviewValidationException {

        String value = parameterParser.get(key);

        for (int i = 0; i < options.length; i++) {
            if (options[i].getValue().equals(value)) {
                return true;
            }
        }

        validationResults.addMessage(key, PLEASE_PICK_A_VALID_PRIORITY);
        return false;
    }

}