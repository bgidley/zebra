/*
 * Created on 03-Aug-2004
 *
 */
package com.anite.antelope.validation;

import java.sql.Date;

import org.apache.commons.lang.StringUtils;
import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

import com.anite.antelope.utils.CalendarHelper;
import com.anite.penguin.formInformation.MaxLength;
import com.anite.penguin.formInformation.Size;

/**
 * @author john.rae created 03-Aug-2004
 */
public class FormattedDateValidator extends AbstractBasePerFieldValidator
        implements MaxLength, Size {

    /**
     * constant for "This field is not allowed to be blank."
     */
    private static final String MESSAGE_FAIL = "This field is not allowed to be blank.";

    /**
     * constant for "errorMessage"
     */
    private static final String PARAM_ISNULLMESSAGE = "failedMessage";

    /**
     * constant for "value"
     */
    private static final String PARAM_CHKVAL = "value";

    /**
     * constant for "allowNull"
     */
    private static final String ALLOWNULL = "allowNull";

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.component.review.main.api.Validator#checkArguments()
     */
    public void doCheckArguments() throws ReviewConfigurationException {

        //If we don't have a message not much point in running as will tell
        // user nothing
        if (args.containsKey(PARAM_ISNULLMESSAGE)) {
            if (StringUtils.isEmpty((String) args.get(PARAM_ISNULLMESSAGE))) {
                throw new ReviewConfigurationException(PARAM_ISNULLMESSAGE
                        + " argument for date validator is empty");
            }
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.component.review.main.api.Validator#validate(org.apache.turbine.util.parser.ParameterParser, java.lang.String,
     *      org.apache.turbine.component.review.util.ValidationResults)
     */
    public boolean doValidate(ParameterParser params, String key,
            ValidationResults validationData) throws ReviewValidationException {

        boolean allowNull = false;

        String keyToCheck = key;

        if (params.containsKey(key)) {
            keyToCheck = params.get(key).toString();
        }

        if (args.containsKey(ALLOWNULL))
            if (args.get(ALLOWNULL).equals("true"))
                allowNull = true;

        if ((keyToCheck == null || keyToCheck.equals("")) && allowNull)
            return true;

        try {
            Date value = CalendarHelper.getInstance().parseDate(keyToCheck);
            if (value != null) {
                return true;
            }
            validationData.addMessage(key, (String) args
                    .get(PARAM_ISNULLMESSAGE));
            return false;

        } catch (Exception e) {
            validationData.addMessage(key, (String) args
                    .get(PARAM_ISNULLMESSAGE));
            return false;
        }

    }

    /* (non-Javadoc)
     * @see com.anite.penguin.formInformation.MaxLength#getMaxLength()
     */
    public String getMaxLength() {
        return "30";
    }

    /* (non-Javadoc)
     * @see com.anite.penguin.formInformation.Size#getSize()
     */
    public String getSize() {
        return "10";
    }
}