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

import org.apache.commons.lang.StringEscapeUtils;


/**
 * Created 20-May-2004
 */
public class Option implements Serializable {
    /** Version Flag for serialisation   */
    static final long serialVersionUID = 1L;

    
    private String value = "";
    private String caption = "";
    
    /**
     * Returns values
     */
    public String toString() {
        return value;
    }
    /**
     * @return Returns the value.
     */
    public String getValue() {
        return value;
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
     * @param value The value to set.
     */
    public void setValue(String value) {
        this.value = value;
    }
    /**
     * @return Returns the caption.
     */
    public String getCaption() {
        return caption;
    }
    
    /**
     * Gets the value as a HTML Safe String
     * @return
     */
    public String getHTMLSafeCaption(){
        return StringEscapeUtils.escapeHtml(this.caption);
    }
    
    /**
     * Get the JavaScript safe value
     * @return
     */
    public String getJavaScriptSafeCaption(){
        return StringEscapeUtils.escapeJavaScript(this.caption);
    }
    
    /**
     * @param caption The caption to set.
     */
    public void setCaption(String caption) {
        this.caption = caption;
    }
}
