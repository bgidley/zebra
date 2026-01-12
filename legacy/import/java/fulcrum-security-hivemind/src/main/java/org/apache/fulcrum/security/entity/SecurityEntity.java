package org.apache.fulcrum.security.entity;

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
 * This classes is the base class for any security entity including
 * groups, users, roles and permissions (and potentially others depending
 * on the model chosen)
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:Rafal.Krzewski@e-point.pl">Rafal Krzewski</a>
 * @author <a href="mailto:hps@intermeta.de">Henning P. Schmiedehausen</a>
 * @author <a href="mailto:marco@intermeta.de">Marco Kn&uuml;ttel</a>
 * @version $Id: SecurityEntity.java,v 1.2 2006/03/18 16:19:37 biggus_richus Exp $
 */

public interface SecurityEntity
{
    /**
     * Get the Name of the SecurityEntity.
     *
     * @return The Name of the SecurityEntity.
     */
    String getName();

    /**
     * Sets the Name of the SecurityEntity.
     *
     * @param name Name of the SecurityEntity.
     */
    void setName(String name);

    /**
     * Get the Id of the SecurityEntity.
     *
     * @return The Id of the SecurityEntity.
     */
    Object getId();

    /**
     * Sets the Id of the SecurityEntity.
     *
     * @param id The new Id of the SecurityEntity
     */
    void setId(Object id);
    
    /**
     * 
     * @return Whether the SecurityEntity is disabled
     *
     * @author richard.brooks
     * Created on 17-Mar-2006
     */
    boolean isDisabled();
    
    /**
     * 
     * @param disabled Whether the SecurityEntity is diabled
     *
     * @author richard.brooks
     * Created on 17-Mar-2006
     */
    void setDisabled(boolean disabled);
}
