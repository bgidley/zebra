/*
 * Created on 03-Aug-2004
 *
 * TODO To change the template for this generated file go to
 * Window - Preferences - Java - Code Style - Code Templates
 */
package com.anite.antelope.validation;

import org.apache.commons.lang.StringUtils;
import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;
import org.apache.turbine.component.review.main.api.ReviewValidationException;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.util.parser.ParameterParser;

/**
 * @author john.rae created 03-Aug-2004
 */
public class IntegerValidator extends AbstractBasePerFieldValidator {

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
				throw new ReviewConfigurationException(PARAM_ISNULLMESSAGE + " argument for integer validator is empty");
			}
		}
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.component.review.main.api.Validator#validate(org.apache.turbine.util.parser.ParameterParser, java.lang.String,
	 *      org.apache.turbine.component.review.util.ValidationResults)
	 */
	public boolean doValidate(ParameterParser params, String key, ValidationResults validationData)
			throws ReviewValidationException {

		String keyToCheck = key;		
		if (params.containsKey(key)) {
			keyToCheck = params.get(key).toString();
		} else {
		    return false;
		}

		try {
			Integer.parseInt(keyToCheck);
			return true;
		} catch (NumberFormatException e) {
			validationData.addMessage(key, (String) args.get(PARAM_ISNULLMESSAGE));
			return false;
		}

	}
}