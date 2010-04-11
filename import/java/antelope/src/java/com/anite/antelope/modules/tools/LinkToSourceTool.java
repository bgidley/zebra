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

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.turbine.Turbine;
import org.apache.turbine.modules.Action;
import org.apache.turbine.modules.ActionLoader;
import org.apache.turbine.modules.Screen;
import org.apache.turbine.modules.ScreenLoader;
import org.apache.turbine.services.pull.ApplicationTool;
import org.apache.turbine.services.template.TurbineTemplate;
import org.apache.turbine.util.RunData;

/**
 * A Tool to provide hyperlinks to Mavenised documentation Created 14-May-2004
 * In TurbineResources.properties set
 * 	linkToSourceTool.mavenBaseUrl
 * to point to the base Url of a maven generated site to view the source and javadoc 
 */
public class LinkToSourceTool implements ApplicationTool {

    private String mavenBaseUrl = null;

    private String screenClassSource = "";

    private String screenClassJavaDoc = "";

    private String lastActionSource = "";

    private String lastActionJavaDoc = "";

    private String screenSource = "";

    private static Log log = LogFactory.getLog(LinkToSourceTool.class);

    private static final String SOURCE_BASE = "xref/";

    private static final String JAVADOC_BASE = "apidocs/";

    private RunData runData;

    private boolean isScreenInitialised = false;

    private boolean isActionInitialised = false;

    /**
     * Figure out which screen and action have been used. 
     * @see org.apache.turbine.services.pull.ApplicationTool#init(java.lang.Object)
     */
    public void init(Object data) {
        runData = (RunData) data;

        if (mavenBaseUrl == null) {
            mavenBaseUrl = Turbine.getConfiguration().getProperty(
                    "linkToSourceTool.mavenBaseUrl").toString();
        }

        screenClassSource = "";
        screenClassJavaDoc = "";
        lastActionSource = "";
        lastActionJavaDoc = "";
        screenSource = "";

        isScreenInitialised = false;
        isActionInitialised = false;

    }

    /**
     * @param runData
     */
    private void initialiseActionInformation() {
        if (runData.hasAction()) {
            try {
                Action aAction = ActionLoader.getInstance().getInstance(
                        runData.getAction());
                lastActionSource = getSourceUrl(aAction.getClass());

                lastActionJavaDoc = getJavaDocUrl(aAction.getClass());
            } catch (Exception e) {
                log.debug("Unable to figure out Action for linking to Source",
                        e);
            }
        }
    }

    /**
     * @param runData
     */
    private void initialiseScreenInformation() {
        if (!runData.getScreenTemplate().equals("")) {
            screenSource = runData.getContextPath() + "/templates/app/screens/"
                    + runData.getScreenTemplate().replace(',', '/');

            try {
                ScreenLoader screenLoader = ScreenLoader.getInstance();
                String screen = TurbineTemplate.getScreenName(runData
                        .getScreenTemplate());
                Screen aScreen = screenLoader.getInstance(screen);

                screenClassSource = getSourceUrl(aScreen.getClass());

                screenClassJavaDoc = getJavaDocUrl(aScreen.getClass());

            } catch (Exception e) {
                log.debug("Unable to figure out screen for Linking To Source",
                        e);
            }
        }
    }

    private String getSourceUrl(Class clazz) {
        return mavenBaseUrl + SOURCE_BASE + clazz.getName().replace('.', '/')
                + ".html";
    }

    private String getJavaDocUrl(Class clazz) {
        return mavenBaseUrl + JAVADOC_BASE + clazz.getName().replace('.', '/')
                + ".html";
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.turbine.services.pull.ApplicationTool#refresh()
     */
    public void refresh() {
    }

    /**
     * @return Returns the lastActionSource.
     */
    public String getLastActionSource() {
        if (!isActionInitialised) {
            initialiseActionInformation();
        }
        return lastActionSource;
    }

    /**
     * @param lastActionSource
     *            The lastActionSource to set.
     */
    public void setLastActionSource(String lastActionSource) {
        this.lastActionSource = lastActionSource;
    }

    /**
     * @return Returns the screenClassJavaDoc.
     */
    public String getScreenClassJavaDoc() {
        if (!isScreenInitialised) {
            initialiseScreenInformation();
        }
        return screenClassJavaDoc;
    }

    /**
     * @param screenClassJavaDoc
     *            The screenClassJavaDoc to set.
     */
    public void setScreenClassJavaDoc(String screenClassJavaDoc) {
        this.screenClassJavaDoc = screenClassJavaDoc;
    }

    /**
     * @return Returns the screenClassSource.
     */
    public String getScreenClassSource() {
        if (!isScreenInitialised) {
            initialiseScreenInformation();
        }
        return screenClassSource;
    }

    /**
     * @param screenClassSource
     *            The screenClassSource to set.
     */
    public void setScreenClassSource(String screenClassSource) {
        this.screenClassSource = screenClassSource;
    }

    /**
     * @return Returns the screenSource.
     */
    public String getScreenSource() {
        if (!isScreenInitialised) {
            initialiseScreenInformation();
        }
        return screenSource;
    }

    /**
     * @param screenSource
     *            The screenSource to set.
     */
    public void setScreenSource(String screenSource) {
        this.screenSource = screenSource;
    }

    /**
     * @return Returns the lastActionJavaDoc.
     */
    public String getLastActionJavaDoc() {
        if (!isActionInitialised) {
            initialiseActionInformation();
        }
        return lastActionJavaDoc;
    }

    /**
     * @param lastActionJavaDoc
     *            The lastActionJavaDoc to set.
     */
    public void setLastActionJavaDoc(String lastActionJavaDoc) {
        this.lastActionJavaDoc = lastActionJavaDoc;
    }
}