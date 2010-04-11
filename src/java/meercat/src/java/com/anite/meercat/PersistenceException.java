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
 
 /**
 * Meercat is a hibernate session manager. It provides a long
 * lasting session for each HTTP session.
 * The session is bound to a thread local for each request - so
 * it available even to classes without direct access to the http
 * session
 * 
 * It requires a filter and a session listener to be registered in 
 * web.xml
 * 
 * <code>
 * <filter>
 *      <filter-name>Hibernate Session Filter</filter-name>
 *      <filter-class>com.aniteps.ctms.utils.persistence.PersistenceTidyUpFilter</filter-class>
 *	</filter>
 *	<filter-mapping>
 *		<filter-name>Hibernate Session Filter</filter-name>
 *		<url-pattern>/*</url-pattern>
 *	</filter-mapping>
 *  <listener>
 *		<listener-class>
 *			com.aniteps.ctms.utils.persistence.PersistenceSessionListener
 *		</listener-class>
 *	</listener>	
 * </code>
 */
package com.anite.meercat;

import org.apache.commons.lang.exception.NestableException;

/**
 * A PersistenceException that is thrown by PersistenceLocator
 */
public class PersistenceException extends NestableException {

    public PersistenceException(String message, Throwable nestedException) {
        super(message, nestedException);
    }

    /**
     * @param string
     */
    public PersistenceException(String message) {
        super(message);
    }

}
