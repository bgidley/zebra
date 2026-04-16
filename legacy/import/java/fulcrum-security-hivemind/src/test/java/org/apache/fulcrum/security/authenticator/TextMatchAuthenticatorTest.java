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

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;

import junit.framework.TestCase;


/**
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: TextMatchAuthenticatorTest.java,v 1.3 2006/01/17 09:17:23 biggus_richus Exp $
 */
public class TextMatchAuthenticatorTest extends TestCase
{
    private static final String password = "myPassword";

    private Authenticator authenticator;
	private User user;
	
    /**
    	* Constructor for CryptoAuthenticatorTest.
    	* @param arg0
    	*/
    public TextMatchAuthenticatorTest(String arg0) {
        super(arg0);
    }
    
    public void setUp() {
        user = new DynamicUser();
        user.setName("Bob");
        user.setPassword(password);
    	authenticator = (Authenticator) RegistryManager.getInstance().getRegistry().getService("fulcrum.security.authenticatorTextMatch", Authenticator.class);;
    }

    public void testAuthenticate() throws Exception
    {
    	User user = new DynamicUser();
    	user.setName("Bob");
    	user.setPassword("myPassword");
		assertTrue(authenticator.authenticate(user,"myPassword"));
		assertFalse(authenticator.authenticate(user,"mypassword"));
    }

    public void testGetCryptoPassword() throws Exception {
    	assertEquals(authenticator.getCryptoPassword(password), password);
    }
}
