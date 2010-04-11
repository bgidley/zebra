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

/*
 * Created on Nov 29, 2004
 *
 */
package com.anite.antelope.validation;

import org.apache.turbine.component.review.datastore.api.ReviewConfigurationException;


/**
 * @author Shaun.Campbell
 *  
 */
public class MoneyValidator extends RegexMaskStringValidator {


    public final void doCheckArguments() throws ReviewConfigurationException {
 
        String regexMask = 
            "^\\$?\\-?((\\.\\d{0,2})?|[1-9]{1}\\d{0,}(\\.\\d{0,2})?|0(\\.\\d{0,2})?|(\\.\\d{1,2})?)$|" + 
            "^\\(\\$?((\\.\\d{0,2})?|[1-9]{1}\\d{0,}(\\.\\d{0,2})?|0(\\.\\d{0,2})?|(\\.\\d{1,2})?)\\)$";
        args.put("regexMask", regexMask);
        super.doCheckArguments();

    }

 }