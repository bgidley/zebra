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
import java.io.Serializable;
import java.util.Date;
import java.util.List;
/**
 * This interface represents the basic functionality of a user.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: User.java,v 1.3 2006/01/24 11:38:53 biggus_richus Exp $
 */
public interface User extends Serializable, SecurityEntity
{
    /**
    * Returns the user's password. This method should not be used by
    * the application directly, because it's meaning depends upon
    * the implementation of UserManager that manages this particular
    * user object. Some implementations will use this attribute for
    * storing a password encrypted in some way, other will not use
    * it at all, when user entered password is presented to some external
    * authority (like NT domain controller) to validate it.
    * See also {@link org.apache.fulcrum.security.UserManager#authenticate(User,String)}.
    *
    * @return A String with the password for the user.
    */
    String getPassword();
   
    /**
     * Set password. Application should not use this method
     * directly, see {@link #getPassword()}.
     * See also {@link org.apache.fulcrum.security.UserManager#changePassword(User,String,String)}.
     *
     * @param password The new password.
     */
    void setPassword(String password);
    
    /**
     * 
     * @return The date on which the user's password expires.
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    Date getPasswordExpiryDate();
    
    /**
     * 
     * @param expiryDate The date the user's password is due to expire.
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    void setPasswordExpiryDate(Date expiryDate);
    
    /**
     * 
     * @return The date the user was locked
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    long getLockTime();
    
    /**
     * 
     * @param locked Date of locking.
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    void setLockTime(long locked);
    
    /**
     * 
     * @return A list of the user's most recent passwords.
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    List getPasswordHistory();
    
    /**
     * 
     * @param passwordHistory List of passwords.
     *
     * @author richard.brooks
     * Created on Jan 12, 2006
     */
    void setPasswordHistory(List passwordHistory);
    
    /**
     * Gets the number of sequential failed login attempts.
     * 
     * @return number of failed login attempts
     *
     * @author richard.brooks
     * Created on Jan 16, 2006
     */
    int getLoginAttempts();
    
    /**
     * Sets the number of failed login attempts.
     * 
     * @param loginAttempts number of failed login attempts.
     *
     * @author richard.brooks
     * Created on Jan 16, 2006
     */
    void setLoginAttempts(int loginAttempts);
}
