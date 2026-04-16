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

package com.anite.penguin.form;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import org.apache.commons.lang.StringEscapeUtils;
import org.apache.commons.lang.StringUtils;

import com.anite.penguin.modules.tools.FormTool;

/**
 * This represents a form field
 * 
 * The concept is it will be supplied by the $form pull tool to provide
 * information to the form designer.
 * 
 * This is a generic field. Not all properties apply to all HTML controls It is
 * up to the form designer to choose which ones to use or not to use
 * 
 * For the meaning of specific fields see the HTML specifiction at www.w3c.org.
 * If the field differs from the specifiction it will state so in the javadoc
 * for the get.
 * 
 * Created 27-Apr-2004
 */
public class Field implements Serializable {

    /** Version Flag for serialisation   */
    static final long serialVersionUID = 1L;
    
    /* Common HTML Items */

    private static final String CHECKED = "checked=\"checked\"";

    private static final String SELECTED = "selected=\"selected\"";

    private String id = "";

    private String htmlClass = "";

    private String style = "";

    private String title = "";

    /* Field Related Items */
    private String name = "";

    private String value = "";

    private String[] values = new String[0];

    private String quickHelp = "";

    private String accessKey = "";

    private boolean disabled = false;

    private boolean readOnly = false;

    private int tabIndex = 0;

    private String size = "";

    private String maxLength = "";

    private Option[] options = new Option[0];

    /* Validation related items */
    private List messages = new ArrayList();

    private boolean isValid = true;

    private boolean isDefault = true;

    private FormTool form;

    public Field() {
    }

    /**
     * Use this constructor normally - as normally a field
     * will have at least a form and name
     * @param form
     * @param name
     */
    public Field(FormTool form, String name) {
        this.setForm(form);
        this.setName(name);
    }
    
    public Field(Field field){
        // Copy all properties over from that field to this
        if (field.id != null){
            this.id = new String(field.id);
        }
        if (field.htmlClass != null){
            this.htmlClass = new String(field.htmlClass);
        }
        if (field.style != null){
            this.style = new String(field.style);
        }
        if (field.title != null) {
            this.title = new String(field.title);
        }
        if (field.name != null) {
            this.name = new String(field.name);
        }
        if (field.value != null) {
            this.value = new String(field.value);
        }
        if (field.values.length > 0) {
            this.values = new String[field.values.length];
            for (int i = 0; i < field.values.length;i++){
                this.values[i] = new String(field.values[i]);
            }
        }
        if (field.quickHelp != null) {
            this.quickHelp = new String(field.quickHelp);
        }
        if (field.accessKey != null) {
        	this.accessKey = new String(field.accessKey);
        }
        this.disabled = field.disabled;
        this.readOnly = field.readOnly;
        this.tabIndex = field.tabIndex;
        if (field.size != null) {
            this.size = new String(field.size);
        }
        if (field.maxLength != null) {
            this.maxLength = new String(field.maxLength);
        }
        this.options = field.options;
        if (field.options.length > 0) {
            this.options = new Option[field.options.length];
            for (int i = 0; i < field.options.length;i++){
                this.options[i] = new Option();
                this.options[i].setValue(field.options[i].getValue());
                this.options[i].setCaption(field.options[i].getCaption());
            }
        }
        
        if (field.messages.size() > 0){
            for (int i = 0; i < field.messages.size(); i++) {
                this.messages.add(i, new String((String)field.messages.get(i)));
             }
        }
        this.isValid = field.isValid;
        this.isDefault = field.isDefault;
        this.form = field.form;

    }

    /**
     * @return Returns the accessKey.
     */
    public String getAccessKey() {
        return accessKey;
    }

    /**
     * @param accessKey
     *            The accessKey to set.
     */
    public void setAccessKey(String accessKey) {
        this.accessKey = accessKey;
    }

    /**
     * @return Returns the disabled.
     */
    public boolean isDisabled() {
        return disabled;
    }

    /**
     * @param disabled
     *            The disabled to set.
     */
    public void setDisabled(boolean disabled) {
        this.disabled = disabled;
    }

    /**
     * @return Returns the readOnly.
     */
    public boolean isReadOnly() {
        return readOnly;
    }

    /**
     * @param readOnly
     *            The readOnly to set.
     */
    public void setReadOnly(boolean readOnly) {
        this.readOnly = readOnly;
    }

    /**
     * @return Returns the htmlClass.
     */
    public String getHtmlClass() {
        return htmlClass;
    }

    /**
     * @param htmlClass
     *            The htmlClass to set.
     */
    public void setHtmlClass(String htmlClass) {
        this.htmlClass = htmlClass;
    }

    /**
     * @return Returns the id.
     */
    public String getId() {
        return id;
    }

    /**
     * @param id
     *            The id to set.
     */
    public void setId(String id) {
        this.id = id;
    }

    /**
     * @return Returns the name.
     */
    public String getName() {
        return name;
    }
    
    public String getNameWithoutSuffix(){
        int offsetLeft = this.getName().lastIndexOf("[");
        int offsetRight = this.getName().lastIndexOf("]");

        if (offsetRight <= offsetLeft + 1) {
            return this.getName();
        } else {
            return this.getName().substring(0, offsetLeft);
        }
    }

    /**
     * @param name
     *            The name to set.
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * A non HTML element used in some application to provide a hyperlink or pop
     * up help for a field. The contents is application specific
     * 
     * @return Returns the quickHelp.
     */
    public String getQuickHelp() {
        return quickHelp;
    }

    /**
     * @param quickHelp
     *            The quickHelp to set.
     */
    public void setQuickHelp(String quickHelp) {
        this.quickHelp = quickHelp;
    }

    /**
     * @return Returns the style.
     */
    public String getStyle() {
        return style;
    }

    /**
     * @param style
     *            The style to set.
     */
    public void setStyle(String style) {
        this.style = style;
    }

    /**
     * @return Returns the tabIndex.
     */
    public int getTabIndex() {
        return tabIndex;
    }

    /**
     * @param tabIndex
     *            The tabIndex to set.
     */
    public void setTabIndex(int tabIndex) {
        this.tabIndex = tabIndex;
    }

    /**
     * @return Returns the title.
     */
    public String getTitle() {
        return title;
    }

    /**
     * @param title
     *            The title to set.
     */
    public void setTitle(String title) {
        this.title = title;
    }

    /**
     * @return Returns the value.
     */
    public String getValue() {
        return value;
    }

    /**
     * @param value
     *            The value to set.
     */
    public void setValue(String value) {
    	if (value == null){
    		this.value = "";
    	} else {
    		this.value = value;
    	}
    	
    	String[] values = new String[1];
        values[0]= this.value;
        setValues(values);
    }
    
    /**
     * Gets the value as a HTML Safe String
     * @return
     */
    public String getHTMLSafeValue(){
        return StringEscapeUtils.escapeHtml(this.value);
    }
    
    /**
     * Get the JavaScript safe value
     * @return
     */
    public String getJavaScriptSafeValue(){
        return StringEscapeUtils.escapeJavaScript(this.value);
    }

    /**
     * True is there are no validation messages for this field currently
     * 
     * @return Returns the isValid.
     */
    public boolean isValid() {
        return isValid;
    }

    /**
     * @param isValid
     *            The isValid to set.
     */
    public void setValid(boolean isValid) {
        this.isValid = isValid;
    }

    /**
     * Returns a List of String messages
     * 
     * @return Returns the messages.
     */
    public List getMessages() {
        return messages;
    }

    /**
     * @param messages
     *            The messages to set.
     */
    public void setMessages(List messages) {
        this.messages = messages;
    }

    /**
     * Add a message to this field Sets this field valid Sets the form not all
     * valid
     * 
     * @param message
     */
    public void addMessage(String message) {
        if (this.form != null) {
            this.form.setAllValid(false);
        }
        this.setValid(false);
        this.messages.add(message);
    }

    /**
     * Set the default value for this field if it is not passed from a previous
     * submit
     * 
     * @return
     */
    public void setDefaultValue(String defaultValue) {
        if (this.isDefault) {
        	setValue(defaultValue);
        }
    }

    /**
     * Set the default values for this field if it is not passed from a previous
     * submit
     * 
     * @param defaultValues
     */
    public void setDefaultValues(String[] defaultValues) {
        if (this.isDefault) {
            this.values = defaultValues;
        }
    }

    /**
     * This has values if there are multiple
     * 
     * @return Returns the values.
     */
    public String[] getValues() {
        return values;
    }

    /**
     * @param values
     *            The values to set.
     */
    public void setValues(String[] values) {
        this.values = values;
    }
    
    /**
     * Returns values escapted for HTML
     * @return
     */
    public String[] getHTMLValues(){
        String[] htmlValues = new String[values.length];
        for (int i = 0; i < htmlValues.length; i++) {
            htmlValues[i] = StringEscapeUtils.escapeHtml(values[i]);
        }
        return htmlValues;
    }
    
    /**
     * Returns values escapted for javascript
     * @return
     */
    public String[] getJavaScriptValues(){
        String[] javaScriptValues = new String[values.length];
        for (int i = 0; i < javaScriptValues.length; i++) {
            javaScriptValues[i] = StringEscapeUtils.escapeJavaScript(values[i]);
        }
        return javaScriptValues;
    }

    /**
     * Helper function to return "checked" if value is in values It can be
     * called from radio buttons and check box controls.
     * 
     * @param value
     * @return
     */
    public String isChecked(String value) {
        // We can always uses the array as values is always filled by validation
        for (int i = 0; i < values.length; i++) {
            if (values[i].equals(value)) {
                return CHECKED;
            }
        }
        return "";
    }

    /**
     * Returns the HTML attribute for selected within an option group
     * @param value
     * @return
     */
    public String isSelected(String value) {
        // We can always uses the array as values is always filled by validation
        for (int i = 0; i < values.length; i++) {
            if (values[i].equals(value)) {
                return SELECTED;
            }
        }
        return "";
    }

    /**
     * Returns true if this is the default value for the field
     * 
     * @return Returns the isDefault.
     */
    public boolean isDefault() {
        return isDefault;
    }

    /**
     * @param isDefault
     *            The isDefault to set.
     */
    public void setDefault(boolean isDefault) {
        this.isDefault = isDefault;
    }

    /**
     * @return Returns the form.
     */
    public FormTool getForm() {
        return form;
    }

    /**
     * @param form
     *            The form to set.
     */
    public void setForm(FormTool form) {
        this.form = form;
    }

    /**
     * @return Returns the size.
     */
    public String getSize() {
        return size;
    }

    /**
     * @param size
     *            The size to set.
     */
    public void setSize(String size) {
        this.size = size;
    }

    /**
     * @return Returns the maxLength.
     */
    public String getMaxLength() {
        return maxLength;
    }

    /**
     * @param maxLength
     *            The maxLength to set.
     */
    public void setMaxLength(String maxLength) {
        this.maxLength = maxLength;
    }

    /**
     * @return Returns the options.
     */
    public Option[] getOptions() {
        return options;
    }

    /**
     * @param options
     *            The options to set.
     */
    public void setOptions(Option[] options) {
        this.options = options;
    }

    /**
     * Returns true if the options on this field contain option groups
     * 
     * @return
     */
    public boolean hasOptionGroups() {
        for (int i = 0; i < options.length; i++) {
            if (options[i] instanceof OptionGroup) {
                return true;
            }
        }
        return false;
    }

    /**
     * Returns the value between the [] if using the field[N] notation
     * @return
     */
    public String getMultipleNameSuffix() {
        int offsetLeft = this.getName().lastIndexOf("[");
        int offsetRight = this.getName().lastIndexOf("]");

        if (offsetRight <= offsetLeft + 1) {
            return "";
        } else {
            return this.getName().substring(offsetLeft + 1, offsetRight);
        }
    }
    
    /**
     * Reset the value of this field to the initalisation params
     * Resets value, values and messages/isValid
     */     
    public void reset(){        
        value = "";
        values = new String[0];
        /* Validation related items */
        messages = new ArrayList();
        isValid = true;
        isDefault=true;
    }
    
    /**
     * Simple function to test if this field is empty.
     * @return
     */
    public boolean isEmpty(){
        return StringUtils.isEmpty(value);                
    }
}