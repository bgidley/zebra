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
package com.anite.ocelot;

import java.io.IOException;

import javax.servlet.ServletOutputStream;
import javax.servlet.ServletResponseWrapper;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * @author Matthew.Norris
 */
public class CachedServletResponse extends ServletResponseWrapper {

    /** logging */
    private static Log log = LogFactory.getLog(CachedServletResponse.class);

    private CachedPrintWriter pw = null;

    /**
     * @param arg0
     */
    public CachedServletResponse(javax.servlet.ServletResponse arg0) {
        super(arg0);
        if (log.isInfoEnabled()) {
            log.info("CachedServletResponse");
        }
        try {
            pw = new CachedPrintWriter(arg0.getWriter());
        } catch (IOException e) {
            log.error("Exception caught :" + e.getMessage(), e);
        }

    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponseWrapper#setResponse(javax.servlet.ServletResponse)
     */
    /**
     * {@inheritDoc}
     */
    public void setResponse(javax.servlet.ServletResponse arg0) {

        super.setResponse(arg0);

        if (log.isInfoEnabled()) {
            log.info("setResponse");
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponse#getWriter()
     */
    /**
     * {@inheritDoc}
     */
    public java.io.PrintWriter getWriter() throws IOException {
        if (log.isInfoEnabled()) {
            log.info("getWriter");
        }
        return this.pw;
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponse#getOutputStream()
     */
    /**
     * {@inheritDoc}
     */
    public ServletOutputStream getOutputStream() throws IOException {
        if (log.isInfoEnabled()) {
            log.info("getOutputStream");
        }
        return super.getOutputStream();
    }

}
