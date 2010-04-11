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
package com.anite.antelope.modules.tools;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.StringUtils;
import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.fulcrum.security.GroupManager;
import org.apache.fulcrum.security.ModelManager;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.RoleManager;
import org.apache.fulcrum.security.SecurityService;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.services.TurbineServices;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;
import org.apache.turbine.services.pull.ApplicationTool;
import org.apache.turbine.util.RunData;

import com.anite.antelope.utils.Cache;

/**
 * @author <a href="mailTo:michael.jones@anite.com">Michael.Jones </a>
 *  
 */
public class SecurityTool implements ApplicationTool {

	public final static String DEFAULT_TOOL_NAME = "security";

	private Cache cache;

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.services.pull.ApplicationTool#init(java.lang.Object)
	 */
	public void init(Object data) {

		cache = new Cache() {

			protected Object create(Object key) {
				Class clazz = (Class) key;
				if (clazz.getName().equals(SecurityService.class.getName())) {
					AvalonComponentService acs = (AvalonComponentService) TurbineServices
							.getInstance().getService(
									AvalonComponentService.SERVICE_NAME);

					SecurityService securityService;
					try {
						securityService = (SecurityService) acs
								.lookup(SecurityService.ROLE);
					} catch (ComponentException ce) {
						throw new NestableRuntimeException(ce);
					}
					return securityService;
				} else {
					return null;
				}
			}
		};
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see org.apache.turbine.services.pull.ApplicationTool#refresh()
	 */
	public void refresh() {

	}

	public boolean isAnonUser(RunData data) {
		return (data.getUser() == null)
				|| StringUtils.isEmpty(data.getUser().getName());
	}
	
	/**
	 * This method checks if the logged in user the named permission
	 * 
	 * @param data the RunData object containing the logged in user
	 * @param permissionName the name of the pemission
	 * @return
	 */
	public boolean hasPermission(RunData data, String permissionName){
		Permission permission;
		try {
			permission = getPermissionManager().getPermissionByName(permissionName);
		} catch (DataBackendException e) {
			throw new NestableRuntimeException(e);
		} catch (UnknownEntityException e) {
			throw new NestableRuntimeException(e);
		}
		return hasPermission(data, permission);		
	}

	/**
	 * This method checks if the logged in user the specified permission
	 * 
	 * @param data the RunData object containing the logged in user
	 * @param permission the Permission to check 
	 * @return
	 */
	public boolean hasPermission(RunData data, Permission permission) {
		// Before doing anything else check that
		// the data contains a user
		if (isAnonUser(data)) {
			return false;
		}
		User user;
		try {
			user = getUserManager().getUser(data.getUser().getName());
		} catch (UnknownEntityException e) {
			throw new NestableRuntimeException();
		} catch (DataBackendException e) {
			throw new NestableRuntimeException();
		}
		return hasPermission(user, permission);
	}

	/**
	 * 
	 * @param user
	 * @param permission
	 * @return
	 */
	public boolean hasPermission(User user, Permission permission) {
		DynamicAccessControlList dacl;
		try {
			dacl = (DynamicAccessControlList) getUserManager().getACL(user);
		} catch (UnknownEntityException e) {
			throw new NestableRuntimeException();
		}
		return dacl.hasPermission(permission);		
	}

	/**
	 * @return Returns the userManager.
	 */
	public UserManager getUserManager() {
		return ((SecurityService) cache.get(SecurityService.class))
				.getUserManager();
	}

	/**
	 * @return Returns the groupManager.
	 */
	public GroupManager getGroupManager() {
		return ((SecurityService) cache.get(SecurityService.class))
				.getGroupManager();
	}

	/**
	 * @return Returns the permissionManager.
	 */
	public PermissionManager getPermissionManager() {
		return ((SecurityService) cache.get(SecurityService.class))
				.getPermissionManager();
	}

	/**
	 * @return Returns the roleManager.
	 */
	public RoleManager getRoleManager() {
		return ((SecurityService) cache.get(SecurityService.class))
				.getRoleManager();
	}
	/**
	 * @return Returns the roleManager.
	 */
	public ModelManager getModelManager() {
		return ((SecurityService) cache.get(SecurityService.class))
				.getModelManager();
	}
}