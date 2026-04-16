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

package com.anite.penguin.modules.tools.validationImpl;

import java.util.Iterator;
import java.util.List;
import java.util.Map;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.component.review.main.api.ReviewService;
import org.apache.turbine.component.review.main.api.Validator;
import org.apache.turbine.component.review.main.impl.ParameterValidator;
import org.apache.turbine.component.review.util.ReviewValve;
import org.apache.turbine.component.review.util.ValidationResults;
import org.apache.turbine.pipeline.PipelineData;
import org.apache.turbine.services.TurbineServices;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;
import org.apache.turbine.services.avaloncomponent.TurbineAvalonComponentService;
import org.apache.turbine.util.RunData;

import com.anite.penguin.exceptions.UnableToInitialiseFormToolException;
import com.anite.penguin.form.Field;
import com.anite.penguin.form.MissingField;
import com.anite.penguin.formInformation.AccessKey;
import com.anite.penguin.formInformation.DefaultValue;
import com.anite.penguin.formInformation.Disabled;
import com.anite.penguin.formInformation.HtmlClass;
import com.anite.penguin.formInformation.Id;
import com.anite.penguin.formInformation.MaxLength;
import com.anite.penguin.formInformation.Name;
import com.anite.penguin.formInformation.Options;
import com.anite.penguin.formInformation.QuickHelp;
import com.anite.penguin.formInformation.Size;
import com.anite.penguin.formInformation.Style;
import com.anite.penguin.formInformation.TabIndex;
import com.anite.penguin.formInformation.Title;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;
import com.anite.penguin.screenEndPoint.api.ScreenEndPoint;

/**
 * This will initialise the tool based on Turbine Review
 * 
 * Each validator can optionally implement the interfaces in
 * com.anite.penguin.formInformation. If it does so the information returned
 * will be set on the field.
 * 
 * It is intended this is used to prevent duplication of information. This is
 * not intended as a form generation solution. Instead it allows certain common
 * values (e.g. max size) to be passed to the form to avoid the validation and
 * the form getting out of sync.
 * 
 * When used with validators currently not utilising this tool it is recommended
 * to extend them and implement the interface on the child class.
 * 
 * Created 27-Apr-2004
 */
public class ValidationFormToolInitialisation {

    private static final String ACTION_PREFIX = "action.";

    private static Log log = LogFactory
            .getLog(ValidationFormToolInitialisation.class);

    /**
     * Initialised passed form tool for the current request The tool is designed
     * to never return nulls so we have to add extra code to make sure
     * everything is initialised
     * 
     * @param tool
     *            The FormTool to fille
     * @param data
     *            The RunData of the request to process
     */
    private void initialiseFields(FormTool tool, PipelineData pipelineData, String endpoint)
            throws UnableToInitialiseFormToolException {

        log.debug("Called initialiseFields");

        if (endpoint != null) {
            initialiseFormDetails(tool, endpoint);

            // If validation has any information add it to the fields
            ValidationResults validationResults = getValidationResults(pipelineData);
            if (validationResults.getKeySet().size() > 0) {
                processValidationResults(tool, validationResults);
            }
        }
    }

    /**
     * Initialise form base on tool and data. Automatically figure out endpoint
     * the action will take priority over the screen
     * 
     * @param tool
     * @param data
     * @throws UnableToInitialiseFormToolException
     */
    public void initialiseFields(FormTool tool, PipelineData pipelineData)
            throws UnableToInitialiseFormToolException {

        initialiseFields(tool, pipelineData, getEndPoint(pipelineData));
    }

    public void initialiseFieldsForEndpoint(FormTool tool, PipelineData pipelineData)
            throws UnableToInitialiseFormToolException {

        initialiseFields(tool, pipelineData, getScreenEndpointFromService(pipelineData));
    }

    /**
     * Initialise the form details for passed end point from possible validation
     * 
     * @param tool
     * @param endpoint
     */
    private void initialiseFormDetails(FormTool tool, String endpoint)
            throws UnableToInitialiseFormToolException {
        ReviewService reviewService;
        FieldMap fields = tool.getFields();

        TurbineAvalonComponentService acs = (TurbineAvalonComponentService) TurbineServices
                .getInstance().getService(AvalonComponentService.SERVICE_NAME);
        try {
            reviewService = (ReviewService) acs.lookup(ReviewService.ROLE);

        } catch (ComponentException e) {
            log.error(e);
            throw new UnableToInitialiseFormToolException(e);
        }

        Map parameterValidatorsMap = reviewService.getActionDetails(endpoint);
        Iterator parameterValidators = parameterValidatorsMap.keySet()
                .iterator();

        String basePath = ACTION_PREFIX + endpoint;

        // Iterate over parameter validators (which are expected fields)
        while (parameterValidators.hasNext()) {
            String key = (String) parameterValidators.next();
            if (!key.equals(basePath)) {
                // This is not the request level validator so process

                Field field = new Field();
                field.setForm(tool);
                field.setName(key.substring(basePath.length() + 1));
                fields.put(field.getName(), field);

                // Now examine the validators and see what metadata they have
                // (if any)
                ParameterValidator parameterValidator = (ParameterValidator) parameterValidatorsMap
                        .get(key);
                Iterator validators = parameterValidator.getValidators()
                        .iterator();

                // We will iterate over the validators processing metadata
                // If more than one validator supplied the metadata both
                // will be called and the 2nd will overwrite the first.
                while (validators.hasNext()) {
                    Validator validator = (Validator) validators.next();
                    loadFieldInformation(field, validator);
                }

            }
        }
    }

    /**
     * @param field
     * @param validator
     */
    private void loadFieldInformation(Field field, Validator validator) {
        if (validator instanceof AccessKey) {
            field.setAccessKey(((AccessKey) validator).getAccessKey());
        }
        if (validator instanceof DefaultValue) {
            DefaultValue defaultValue = (DefaultValue) validator;
            field.setDefaultValue(defaultValue.getDefaultValue());
            field.setDefaultValues(defaultValue.getDefaultValues());
        }
        if (validator instanceof Disabled) {
            field.setDisabled(((Disabled) validator).isDisabled());
        }
        if (validator instanceof HtmlClass) {
            field.setHtmlClass(((HtmlClass) validator).getHtmlClass());
        }
        if (validator instanceof Id) {
            field.setId(((Id) validator).getId());
        }
        if (validator instanceof MaxLength) {
            field.setMaxLength(((MaxLength) validator).getMaxLength());
        }
        if (validator instanceof Name) {
            field.setName(((Name) validator).getName());
        }
        if (validator instanceof QuickHelp) {
            field.setQuickHelp(((QuickHelp) validator).getQuickHelp());
        }
        if (validator instanceof Size) {
            field.setSize(((Size) validator).getSize());
        }
        if (validator instanceof Style) {
            field.setStyle(((Style) validator).getStyle());
        }
        if (validator instanceof TabIndex) {
            field.setTabIndex(((TabIndex) validator).getTabIndex());
        }
        if (validator instanceof Title) {
            field.setTitle(((Title) validator).getTitle());
        }
        if (validator instanceof Options) {
            field.setOptions(((Options) validator).getOptions());
        }
    }

    /**
     * Get the endpoint for the current request If this is an action it is easy
     * If this is a screen without an action look it up
     * 
     * @param data
     * @return
     */
    private String getEndPoint(PipelineData pipelineData)
            throws UnableToInitialiseFormToolException {
        Map runDataMap = (Map) pipelineData.get(RunData.class);
        RunData data = (RunData)runDataMap.get(RunData.class);
        if (data.getAction() != "") {
            return data.getAction();
        } else {
            return getScreenEndpointFromService(pipelineData);
        }
    }

    /**
     * Looks up the endpoint from the service based on the screen
     * 
     * @param data
     * @return @throws
     *         UnableToInitialiseFormToolException
     */
    private String getScreenEndpointFromService(PipelineData pipelineData)
            throws UnableToInitialiseFormToolException {
        Map runDataMap = (Map) pipelineData.get(RunData.class);
        RunData data = (RunData)runDataMap.get(RunData.class);        
        TurbineAvalonComponentService acs = (TurbineAvalonComponentService) TurbineServices
                .getInstance().getService(AvalonComponentService.SERVICE_NAME);
        try {
            ScreenEndPoint screenEndPoint = (ScreenEndPoint) acs
                    .lookup(ScreenEndPoint.ROLE);
            return screenEndPoint.getEndPoint(data.getScreenTemplate());
        } catch (ComponentException e) {
            log.error(e);
            throw new UnableToInitialiseFormToolException(e);
        }
    }

    /**
     * @param tool
     * @param validationResults
     */
    private void processValidationResults(FormTool tool,
            ValidationResults validationResults) {
        // Set form level information
        tool.setAllValid(validationResults.isAllValid());
        tool.setRequestMessages(validationResults.getRequestMessages());

        FieldMap fields = tool.getFields();
        Iterator resultsKey = validationResults.getKeySet().iterator();
        while (resultsKey.hasNext()) {
            String result = (String) resultsKey.next();
            populateValidatedField(validationResults, fields, result, tool);
        }
    }

    /**
     * @param validationResults
     * @param fields
     * @param resultsKey
     */
    private void populateValidatedField(ValidationResults validationResults,
            FieldMap fields, String result, FormTool tool) {

        Field field = (Field) fields.get(result);
        if (field instanceof MissingField) {
            if (log.isDebugEnabled()) {
                log.debug("Creating new field in tool as in validation:"
                        + result);
            }
            field = new Field(tool, result);            
            fields.put(result, field);
        }
        field.setMessages(validationResults.getMessages(result));

        if (field.getMessages().size() == 0) {
            field.setValid(true);
        } else {
            field.setValid(false);
        }

        Object fieldValue = validationResults.getValue(result);
        if (fieldValue != null) {
            field.setValue(fieldValue.toString());
        } else {
            field.setValue("");
        }

        List fieldValues = validationResults.getValues(result);
        String[] values;
        if (fieldValues.size() == 0) {
            values = new String[0];
        } else {
            values = new String[fieldValues.size()];
            for (int i = 0; i < fieldValues.size(); i++) {
                values[i] = (String) fieldValues.get(i);
            }
        }
        field.setDefault(false);
        field.setValues(values);
    }

    /**
     * This fetches the validation results from Fulcrum Validation
     * 
     * @param data
     * @return
     */
    private ValidationResults getValidationResults(PipelineData pipelineData) {
        ValidationResults validationResults;
        Map reviewData = (Map) pipelineData.get(ReviewValve.class);
        validationResults = (ValidationResults) reviewData.get(ValidationResults.class);
        return validationResults;
    }
}