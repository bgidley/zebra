package org.apache.fulcrum.security.util;

/*
 *  Copyright 2001-2004 The Apache Software Foundation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

/**
 * Thrown to indicate that there was an error accessing the data
 * backend of the SecurityService.
 *
 * @author <a href="mailto:krzewski@e-point.pl">Rafal Krzewski</a>
 * @version $Id: DataBackendException.java,v 1.2 2006/03/18 16:19:36 biggus_richus Exp $
 */
public class DataBackendException
    extends TurbineSecurityException
{
	private static final long serialVersionUID = 4037968846303489743L;

	/**
     * Construct an DataBackendException with specified detail message.
     *
     * @param msg The detail message.
     */
    public DataBackendException(String msg)
    {
        super(msg);
    }

    /**
     * Construct an DataBackendException with specified detail message
     * and nested <code>Throwable</code>.
     *
     * @param msg The detail message.
     * @param nested the exception or error that caused this exception
     *               to be thrown.
     */
    public DataBackendException(String msg, Throwable nested)
    {
        super(msg, nested);
    }
};
