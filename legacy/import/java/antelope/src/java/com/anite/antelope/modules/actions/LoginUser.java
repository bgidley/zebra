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

package com.anite.antelope.modules.actions;

import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.adapter.turbine.UserAdapter;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.PasswordMismatchException;
import org.apache.turbine.modules.actions.VelocityAction;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;
/**
 * @author Michael.Jones
 */
public class LoginUser extends VelocityAction {
	/**
	 * Tries to log the user in from the user name and password entered on the
	 * login form.
	 * 
	 * @param data
	 * @param context
	 */
	public void doPerform(RunData data, Context context) throws Exception {
		String username;
		String password;
		
		// get the parameters from the fom 
		username = data.getParameters().get("username");
		password = data.getParameters().get("password");
		
		// if the user didnt enter a user name 
		// tell him to 
		if (username.equals("")) {
			data.setMessage("Please your username!");
			data.setScreen("Login.vm");
			return;
		}
		
		SecurityService securityService;
		UserManager usermanager;
		
		// retrieve the fulcrum security service from avalon
		// and then get the usermanager
		securityService = AvalonServiceHelper.instance().getSecurityService();
        usermanager = securityService.getUserManager();
        
		// Check that the name entered is one which is stored in 
        // the usermanager
        if( usermanager.checkExists(username) ) {
        	User user;
        	UserAdapter userAdapter;
        	
        	// Authenticate the user 
        	try {				
	        	user = usermanager.getUser(username);
				usermanager.authenticate(user, password);
	        } catch (PasswordMismatchException pme) {
				data.setMessage("Password incorrect");
				return;
	        }	
	        
	        // Wrap the user in the fulcrum user
	        // adapter for turbine so it can be saved in the 
	        // rundata
	        userAdapter = new UserAdapter(user); 
	        
	        // log the user in, set it as the user in the
	        // rundata and save it				
	        data.setUser(userAdapter);	        
	        data.save();
	        
	        // Tell the user locator
	        UserLocator.setLoggedInUser(user);
	        
	        // set the index page
	        data.setScreenTemplate("Index.vm");
			
		} else { // the user did not exist
			data.setMessage("No such user");						
		}		
	}
}