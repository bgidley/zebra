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

package com.anite.antelope.modules.actions;

import org.apache.commons.configuration.Configuration;
import org.apache.commons.lang.StringUtils;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.Turbine;
import org.apache.turbine.TurbineConstants;
import org.apache.turbine.modules.actions.sessionvalidator.TemplateSessionValidator;
import org.apache.turbine.modules.screens.TemplateScreen;
import org.apache.turbine.services.InitializationException;
import org.apache.turbine.util.RunData;
import org.apache.turbine.util.TurbineException;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.helper.ZebraHelper;

/**
 * Validator implementation that insists everyone always loggs in and initialises the user locator
 * for each and every request
 * 
 * This is in actions - because Turbine insists on it. 
 * @author Ben.Gidley
 */
public class AntelopeSessionValidator extends TemplateSessionValidator {

    private final static Log log = LogFactory.getLog(AntelopeSessionValidator.class);

    /**
     * If logged in set up userLocator
     */
    public void doPerform(RunData data) throws TurbineException {
        super.doPerform(data);

        if (data.getUser() == null || StringUtils.isEmpty(data.getUser().getName())) {

            // Anonymous
            // Check where we are going
            if (data.getAction() == Turbine.getConfiguration().getString(TurbineConstants.ACTION_LOGIN_KEY)) {
                // Ok
            } else {
                //Set the screen template to the login page.
                String loginTemplate = Turbine.getConfiguration().getString(TurbineConstants.TEMPLATE_LOGIN);

                log.debug("Sending User to the Login Screen (" + loginTemplate + ")");
                data.getTemplateInfo().setScreenTemplate(loginTemplate);

                data.setAction(null);
            }
        } else {
            try {
                // Logged in
                UserLocator.setLoggedInUser(getUserManager().getUser(data.getUser().getName()));
                // back button fix
                checkForNoCacheId(data, Turbine.getConfiguration());
               
            } catch (InitializationException e) {
                log.error("", e);
            } catch (UnknownEntityException e) {
                log.error("", e);
            } catch (DataBackendException e) {
                log.error("", e);
            }
        }
    }

    /**
     * @param data
     * @param conf
     */
    private void checkForNoCacheId(RunData data, Configuration conf) {
        long requestTime;
        // the session_access_counter can be placed as a hidden field in
        // forms. This can be used to prevent a user from using the
        // browsers back button and submitting stale data.
        if (!data.getParameters().containsKey("nocacheid")) {
            //can't compare cache ids so return
            return;
        }
        requestTime = data.getParameters().getLong("nocacheid");

        /*
         * The following few lines of code take care of the instances where the
         * request is being forwarded from a servlet (or something similar)
         * within the same context. In this instance, it is possible that the
         * cacheid will not be present in the request parameters. This code
         * tries to obtain the requestTime from the request attributes instead,
         * effectively allowing the forwarded request to successfully pass
         * through this validation. Added by SPC on 16 December 2003 to cater
         * for TRIM integration
         */
        if (requestTime == 0) {
            Long noCache = (Long) data.getRequest().getAttribute("nocacheid");
            if (noCache != null) {
                requestTime = noCache.longValue();
            }
        }

        Long lrt = (Long) data.getSession().getAttribute("lastRequestTime");
        long lastRequestTime = 0;
        if (lrt != null) {
            lastRequestTime = lrt.longValue();
        }
        if (requestTime <= lastRequestTime) {
            if (!((requestTime == 0) && (lastRequestTime == 0))) {
                data.getTemplateInfo().setScreenTemplate(conf.getString(TurbineConstants.TEMPLATE_INVALID_STATE));                
                log.error("Found an invalid request");
                
                data.setScreen(null);
                data.setAction(null);
                
                TemplateScreen.setTemplate(data, ZebraHelper.getInstance().getTaskListScreenName());
               
            }
        }
        data.getSession().setAttribute("lastRequestTime", new Long(requestTime));

    }

    /**
     * @return Returns the userManager.
     * @throws InitializationException
     */
    private UserManager getUserManager() throws InitializationException {
        return AvalonServiceHelper.instance().getSecurityService().getUserManager();
    }

}