package org.apache.fulcrum.security.authenticator;
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
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;
/**
 * This class authenticates by doing a plain text match of the user's passwords.
 * Very insecure! 
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: TextMatchAuthenticator.java,v 1.2 2006/01/17 09:17:24 biggus_richus Exp $
 * @avalon.component name="textmatch-authenticator"
 * @avalon.service type="org.apache.fulcrum.security.authenticator.Authenticator"
 */
public class TextMatchAuthenticator implements Authenticator
{
    /**
     * Authenticate an username with the specified password.  Returns true
     * if the user password plain text matches the passed in password.
     * 
     *
     * @param user object
     * @param password the user supplied password.
     * @exception UnknownEntityException if the user's account does not
     *            exist in the database.
     * @exception DataBackendException if there is a problem accessing the
     *            storage.
     */
    public boolean authenticate(User user, String password) throws  DataBackendException
    {
        if( user == null )
            return false;
        
        String referenced = user.getPassword() == null ? "" : user.getPassword().trim();
        String tested = password == null ? "" : password.trim();
        
        return referenced.equals(tested);
    }

	public String getCryptoPassword(String password) throws DataBackendException {
		return password;
	}
}
