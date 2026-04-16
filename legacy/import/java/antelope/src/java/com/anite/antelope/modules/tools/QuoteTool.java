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
package com.anite.antelope.modules.tools;

import org.apache.turbine.services.pull.ApplicationTool;

/**
 * A stupid tool for displaying tip of the day!!
 * 
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class QuoteTool implements ApplicationTool {

    private String quote;

    private String[] quotes = { "Add new quotes in the QuoteTool.",
            "I do not fear computers. I fear the lack of them.",
            "To err is human--and to blame it on a computer is even more so.",
            "BUG,n.: An undesirable , poorly-understood undocumented feature.",
            "Hard work never killed anybody, but why take a chance?",
            "The secret of creativity is knowing how to hide your sources."};

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.services.pull.ApplicationTool#init(java.lang.Object)
     */
    public void init(Object data) {
        int i = (int) (Math.random() * 10) % quotes.length;
        quote = quotes[i];
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.services.pull.ApplicationTool#refresh()
     */
    public void refresh() {
    }

    public String getQuote() {
        return quote;
    }

}