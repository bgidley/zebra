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

package com.anite.meercat;

import java.io.IOException;

import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.FilterConfig;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.http.HttpServletRequest;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * Filter to attatch and detatch the hibernate session from the thread for a
 * request This filter assumes (which is true in tomcat) that a request remains
 * on the same thread. If this is not true the results will be undefined.
 * 
 * @author Ben.Gidley
 */
public class PersistenceTidyUpFilter implements Filter {

    private static Log log = LogFactory.getLog(PersistenceTidyUpFilter.class);

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.Filter#destroy()
     */
    public void destroy() {

    }

    /**
     * Run all the normal stuf, assoicate hibernate session to thread then on
     * finally close the request.
     * 
     * @see javax.servlet.Filter#doFilter(javax.servlet.ServletRequest,
     *      javax.servlet.ServletResponse, javax.servlet.FilterChain)
     */
    public void doFilter(ServletRequest request, ServletResponse response,
            FilterChain filterChain) throws IOException, ServletException {

        if (log.isInfoEnabled()) {
            log.info("doFilter");
        }

        if (request instanceof HttpServletRequest) {
            HttpServletRequest httpRequest = (HttpServletRequest) request;

            try {
                filterChain.doFilter(request, response);
            } catch (Exception e) {
                log.error("FilterChain generated an error", e);
            }

            // close hibernate session, just in case there is one!
            PersistenceLocator.getInstance().closeRequest();
        } else {
            log.info("Unusual request");
            filterChain.doFilter(request, response);
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see javax.servlet.Filter#init(javax.servlet.FilterConfig)
     */
    public void init(FilterConfig arg0) throws ServletException {

    }

}