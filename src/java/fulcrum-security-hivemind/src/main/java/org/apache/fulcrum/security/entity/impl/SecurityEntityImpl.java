package org.apache.fulcrum.security.entity.impl;
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


import org.apache.commons.lang.builder.HashCodeBuilder;
import org.apache.fulcrum.security.entity.SecurityEntity;

/**
 * Base class for all objects implementing SecurityEnitity.  This
 * class automatically lowercases the name.  So the permission "EDIT"
 * will equal "eDit" and "edit";
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: SecurityEntityImpl.java,v 1.2 2006/03/18 16:19:39 biggus_richus Exp $
 */
public class SecurityEntityImpl implements SecurityEntity
{
    private String name;
    private Object id;
    private boolean disabled;
    
    /**
     * @return
     */
    public Object getId()
    {
        return id;
    }
    /**
     * @param id
     */
    public void setId(Object id)
    {
        this.id = id;
    }
    /**
     * @return
     */
    public String getName()
    {
        return name;
    }
    /**
     * Pass in the name for this entity.  Also lowercases it.
     * @param name
     */
    public void setName(String name)
    {
        if (name !=null){
          // throw new InvalidParameterException("Must provide a valid name for all SecurityEntities.");
		   name = name.toLowerCase();
        }
		this.name = name;
		//this.name = name.toLowerCase();
    }
    public String toString()
    {
        return getClass().getName() + " (id:" + getId() + " name:" + getName()+")";
    }
    public boolean equals(Object o)
    {
        boolean equals = true;
        if (o == null)
        {
            equals = false;
        }
        else
        {
            equals = (getId() == ((SecurityEntityImpl) o).getId());
        }
        return equals;
    }
    public int hashCode(Object o)
    {
        return HashCodeBuilder.reflectionHashCode(this);
    }
    
	public boolean isDisabled() {
		return disabled;
	}
	
	public void setDisabled(boolean disabled) {
		this.disabled = disabled;
	}
}
