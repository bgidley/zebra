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

package com.anite.penguin.modules.tools;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.OutputStreamWriter;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.Turbine;
import org.apache.turbine.pipeline.PipelineData;
import org.apache.turbine.services.pull.PipelineDataApplicationTool;
import org.apache.turbine.util.RunData;

import com.anite.penguin.exceptions.UnableToInitialiseFormToolException;
import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.validationImpl.ValidationFormToolInitialisation;
import com.thoughtworks.xstream.XStream;
import com.thoughtworks.xstream.io.HierarchicalStreamDriver;
import com.thoughtworks.xstream.io.xml.XppDriver;

/**
 * This represents a com.anite.penguin.form to be submitted that uses validation
 * to resolve defaults and current values
 * 
 * @author Ben.Gidley
 * @author Shaun Campbell
 */
public class FormTool implements PipelineDataApplicationTool, Serializable {

    /** Version Flag for serialisation   */
    static final long serialVersionUID = 1L;

    /**
     * Slightly more debugger friendly toString that list the current field 
     * values 
     */
    public String toString() {
        return fields.toString();
    }

    private transient static Log log = LogFactory.getLog(FormTool.class);

    /**
     * The default tool name - this can be used by applications to load an
     * instance of the tool into a screen class to set defaults
     * 
     * If you use this and change the tool name subclass this class and overide
     * the constant or add your own constant somewhere else.
     */
    public transient static final String DEFAULT_TOOL_NAME = "form";

    /**
     * The fields that this com.anite.penguin.form uses this will only contain
     * objects of type field
     */
    private FieldMap fields = new FieldMap();

    private boolean isAllValid = true;

    private List requestMessages = new ArrayList();

    private boolean reinitialise = true;
    
    private transient PipelineData pipelineData;

    public boolean isAllValid() {
        return isAllValid;
    }

    public void setAllValid(boolean allValid) {
        isAllValid = allValid;
    }

    public FieldMap getFields() {
        return fields;
    }

    public void setFields(FieldMap fields) {
        this.fields = fields;
    }

    public List getRequestMessages() {
        return requestMessages;
    }

    public void setRequestMessages(List requestMessages) {
        this.requestMessages = requestMessages;
    }

    /**
     * For Now this tool initialises regardless from the validationFormTool
     * initialisation <p/>It would be nice to Avalon this so that the filling
     * implementation is plugable.
     * 
     * @see org.apache.turbine.services.pull.ApplicationTool#init(java.lang.Object)
     */
    public void init(Object object) {
        if (!(object instanceof PipelineData)) {
            log
                    .error("Unable to initialise FormTool. Requires a PipelineData object.");
            return;
        }

        reinitialise = true;
        RunData data = getRunData((PipelineData) object);
        // Do not do anything if logging in or out - as validation does not work for login/out
        String actionName = data.getAction();
        if (data.hasAction()
                && actionName.equalsIgnoreCase(Turbine.getConfiguration()
                        .getString(Turbine.ACTION_LOGIN_KEY))
                || actionName.equalsIgnoreCase(Turbine.getConfiguration()
                        .getString(Turbine.ACTION_LOGOUT_KEY))) {
            log.debug("Not initialising FormToom as logging in/out");
            return;
        }

        this.pipelineData = (PipelineData) object;
        fields = new FieldMap();
        isAllValid = true;
        requestMessages = new ArrayList();
        try {
            ValidationFormToolInitialisation init = new ValidationFormToolInitialisation();
            init.initialiseFields(this, pipelineData);
        } catch (UnableToInitialiseFormToolException e) {
            // as we are a pull tool silently swallow this
            log.error("Unable to reinitialise Form tool for endpoint", e);
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.services.pull.ApplicationTool#refresh()
     */
    public void refresh(PipelineData pipelineData) {
        // No code here as init is always callled
    }

    /**
     * Reinitialise ignoring the action
     *  
     */
    public void reinitialiseForScreenEndpoint() {

        if (this.pipelineData != null && reinitialise ) {
            reinitialiseForScreenEndpoint(pipelineData);
        } else {
            // We have been serialized
            log
                    .info("Someone attempted to reinitialize a serialised formTool - done nothing");
        }
    }

    public void reinitialiseForScreenEndpoint(PipelineData data) {
        try {
            ValidationFormToolInitialisation init = new ValidationFormToolInitialisation();
            init.initialiseFieldsForEndpoint(this, pipelineData);
        } catch (UnableToInitialiseFormToolException e) {
            // as we are a pull tool silently swallow this
            log.error("Unable to reinitialise Form tool for endpoint", e);
        }
    }

    /**
     * Add a message to this form and marks the form invalid if not already
     * 
     * @param message
     */
    public void addMessage(String message) {
        this.requestMessages.add(message);
        this.setAllValid(false);
    }

    /**
     * Helper method to get a field from the FieldMap
     * @param key
     * @return
     */
    public Field getField(Object key) {
        return (Field) getFields().get(key);
    }

    /**
     * A method to determine which of a multiple button set was clicked
     * and returns the string associated with the button. The string is 
     * enclosed in [].
     * 
     * Multiple button sets have the same name but have a [string]
     * suffix. i.e. buttonname[string1], buttonname[string2] etc. Usually the 
     * string is just numeric buttonname[1], buttonname[2]
     *
     * @param multiButtonName The name of the button less the suffix.
     * @return String - The string appended to the button name
     */
    public String whichButtonClicked(String multiButtonName) {

        Set buttons = getFields().getMultipleFields(multiButtonName);
        Iterator buttonIterator = buttons.iterator();
        while (buttonIterator.hasNext()) {
            Field field = (Field) buttonIterator.next();
            if (!field.getValue().equals("")) {
                return field.getMultipleNameSuffix();
            }
        }
        return "";
    }

    public final RunData getRunData(PipelineData pipelineData) {
        RunData data = null;
        Map runDataMap = (Map) pipelineData.get(RunData.class);
        data = (RunData) runDataMap.get(RunData.class);
        return data;
    }
    
    /**
     * Set this to false to prevent this tool reinitialising ever
     * This is only useful in some rather odd circumstances
     * Where the tool has been serialized and pipeline data somehow survived. 
     * @param reinitialise
     */
    public void setReinitialise(boolean reinitialise) {
        this.reinitialise = reinitialise;
    }
}