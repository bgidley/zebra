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
import java.io.PrintWriter;

import javax.servlet.ServletOutputStream;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletResponseWrapper;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * @author Matthew.Norris
 */
public class CachedHttpResponse extends HttpServletResponseWrapper {

    /** logging */
    private static Log log = LogFactory.getLog(CachedHttpResponse.class);

    private CachedServletResponse csr;

    /**
     * @param arg0
     */
    public CachedHttpResponse(javax.servlet.http.HttpServletResponse arg0) {

        super(arg0);
        csr = new CachedServletResponse(arg0);
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponseWrapper#setResponse(javax.servlet.ServletResponse)
     */
    /**
     * {@inheritDoc}
     */
    public void setResponse(ServletResponse arg0) {
        if (log.isInfoEnabled()) {
            log.info("setResponse");
        }
        csr = new CachedServletResponse(arg0);
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
        return csr.getOutputStream();
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponse#getWriter()
     */
    /**
     * {@inheritDoc}
     */
    public PrintWriter getWriter() throws IOException {
        if (log.isInfoEnabled()) {
            log.info("getWriter");
        }
        return csr.getWriter();
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.ServletResponseWrapper#getResponse()
     */
    /**
     * {@inheritDoc}
     */
    public ServletResponse getResponse() {
        if (log.isInfoEnabled()) {
            log.info("getResponse");
        }
        return csr;
    }

}
