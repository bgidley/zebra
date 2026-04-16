package org.apache.fulcrum.security.session;

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
 * This interface is modelled after
 * {@link javax.servlet.http.HttpSessionBindingListener}.
 *
 * @author <a href="mailto:dlr@finemaltcoding.com">Daniel Rall</a>
* @version $Id: SessionBindingListener.java,v 1.1 2005/11/14 18:20:50 bgidley Exp $
 */
public interface SessionBindingListener
{
    /**
     * Notifies the object that it is being bound to a session and
     * identifies the session.
     *
     * @param event A SessionBindingEvent object.
     */
    void valueBound(SessionBindingEvent event);

    /**
     * Notifies the object that it is being unbound from a session and
     * identifies the session.
     *
     * @param event A SessionBindingEvent object.
     */
    void valueUnbound(SessionBindingEvent event);
}
