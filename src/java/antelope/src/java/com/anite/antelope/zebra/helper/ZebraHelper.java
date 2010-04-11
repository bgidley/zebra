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

package com.anite.antelope.zebra.helper;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Query;
import net.sf.hibernate.Session;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.apache.turbine.services.InitializationException;
import org.apache.turbine.services.TurbineServices;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;

import com.anite.antelope.session.UserLocator;
import com.anite.antelope.utils.AvalonServiceHelper;
import com.anite.antelope.zebra.om.AntelopeProcessDefinition;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.avalon.api.IAvalonDefsFactory;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.factory.api.IStateFactory;

/**
 * Provides a helper interface to common workflow tasks (especially things made
 * harder by avalon)
 * 
 * 
 * @author Matthew.Norris
 * @author Ben Gidley
 */
public class ZebraHelper {

    /**
     * logging
     */
    private static Log log = LogFactory.getLog(ZebraHelper.class);

    private static ZebraHelper instance;

    private ZebraHelper() {
    }

    public static ZebraHelper getInstance() {
        if (instance == null) {
            instance = new ZebraHelper();
        }
        return instance;
    }

    /**
     * Get a process definition by process name
     * 
     * @param name
     * @return @throws
     *         NestableException
     */
    public AntelopeProcessDefinition getProcessDefinition(String name)
            throws NestableException {
        try {
            return (AntelopeProcessDefinition) this.getDefinitionFactory()
                    .getProcessDefinition(name);
        } catch (Exception e) {
            log.error("Failed to load ProcessDef:" + name, e);
            throw new NestableException(e);
        }
    }

    /**
     * Get a task instance by ID
     * 
     * @return Task Instance
     * @throws NestableException
     */
    public AntelopeTaskInstance getTaskInstance(Long taskInstanceId)
            throws NestableException {
        try {
            Session session = PersistenceLocator.getInstance()
                    .getCurrentSession();

            return (AntelopeTaskInstance) session.load(
                    AntelopeTaskInstance.class, taskInstanceId);
        } catch (Exception e) {
            log.error("Failed to load Task Instance:"
                    + taskInstanceId.toString(), e);
            throw new NestableException(e);
        }
    }

    /**
     * Create a process in a paused state
     * 
     * @param processName
     *            process Name
     * @return Process Instance
     */
    public AntelopeProcessInstance createProcessPaused(String processName)
            throws NestableException {
        AntelopeProcessDefinition pd = getProcessDefinition(processName);
        return createProcessPaused(pd);
    }

    /**
     * Create a process in a paused state
     * 
     * @param processDef
     * @return A Process Instance
     * @throws NestableException
     */
    public AntelopeProcessInstance createProcessPaused(
            AntelopeProcessDefinition processDef) throws NestableException {
        try {
            AntelopeProcessInstance processInstance = (AntelopeProcessInstance) this
                    .getEngine().createProcess(processDef);
            return processInstance;
        } catch (Exception e) {
            log.error("Failed to create paused instance of:"
                    + processDef.getName(), e);
            throw new NestableException(e);
        }
    }

    /**
     * Get the Engine via Avalon
     * @return The engine
     * @throws ComponentException
     */
    public IEngine getEngine() throws ComponentException {
        AvalonComponentService acs = (AvalonComponentService) TurbineServices
                .getInstance().getService(AvalonComponentService.SERVICE_NAME);
        try {
            return (IEngine) acs.lookup(IEngine.class.getName());
        } catch (ComponentException ce) {
            log.error("Unable to lookup " + IEngine.class.getName(), ce);
            throw ce;
        }
    }

    /**
     * Gets the Zebra Definitions Factory Service from Avalon
     * @return
     * @throws ComponentException
     */
    public IAvalonDefsFactory getDefinitionFactory() throws ComponentException {
        AvalonComponentService acs = (AvalonComponentService) TurbineServices
                .getInstance().getService(AvalonComponentService.SERVICE_NAME);
        try {
            return (IAvalonDefsFactory) acs.lookup(IAvalonDefsFactory.class
                    .getName());
        } catch (ComponentException ce) {
            log.error("Unable to lookup " + IAvalonDefsFactory.ROLE, ce);
            throw ce;
        }
    }

    /**
     * Get Antelope State Factory from Avalon 
     * @return
     * @throws ComponentException
     */
    public IStateFactory getStateFactory() throws ComponentException {
        AvalonComponentService acs = (AvalonComponentService) TurbineServices
                .getInstance().getService(AvalonComponentService.SERVICE_NAME);
        try {
            return (IStateFactory) acs.lookup(IStateFactory.class.getName());
        } catch (ComponentException ce) {
            log.error("Unable to lookup " + IStateFactory.class.getName(), ce);
            throw ce;
        }
    }

    /**
     * Get the task list for the passed user
     * @param user
     * @return
     * @throws HibernateException
     * @throws NestableException
     */
    public List getTaskList(User user) throws NestableException {

        try {
            Session session = PersistenceLocator.getInstance()
                    .getCurrentSession();
            Query tasks = session.getNamedQuery("AllUsersTasks");
            tasks.setBoolean("show", true);
            
            tasks.setCacheable(true);

            List usersTasks = new ArrayList();

            UserManager manager = AvalonServiceHelper.instance()
                    .getSecurityService().getUserManager();

            DynamicAccessControlList acl = (DynamicAccessControlList) manager
                    .getACL(user);

            Iterator allTasks = tasks.iterate();
            while (allTasks.hasNext()) {
                AntelopeTaskInstance taskInstance = (AntelopeTaskInstance) allTasks
                        .next();
                Iterator taskPermissions = taskInstance.getPermissions()
                        .iterator();
                while (taskPermissions.hasNext()) {
                    if (acl.hasPermission((Permission) taskPermissions.next())) {
                        usersTasks.add(taskInstance);
                        break;
                    }
                }
            }

            return usersTasks;
        } catch (InitializationException e) {
            log.error("Failed to load users service", e);
            throw new NestableException(e);
        } catch (UnknownEntityException e) {
            log.error("User does not exist", e);
            throw new NestableException(e);
        } catch (HibernateException e) {
            log.error("Datastore problems building task list", e);
            throw new NestableException(e);
        }

    }

    /**
     * Get the task list for the passed user
     * @param user
     * @return
     * @throws HibernateException
     * @throws NestableException
     */
    public List getOwnerTaskList(User user) throws NestableException {

        try {
            Session session = PersistenceLocator.getInstance()
                    .getCurrentSession();
            Query tasks = session.getNamedQuery("UsersTasks");
            tasks.setParameter("user", user);
            tasks.setBoolean("show", true);
            tasks.setCacheable(true);

            //return tasks.list();

            List usersTasks = new ArrayList();

            UserManager manager = AvalonServiceHelper.instance()
                    .getSecurityService().getUserManager();

            DynamicAccessControlList acl = (DynamicAccessControlList) manager
                    .getACL(user);

            Iterator allTasks = tasks.iterate();
            while (allTasks.hasNext()) {
                AntelopeTaskInstance taskInstance = (AntelopeTaskInstance) allTasks
                        .next();
                Iterator taskPermissions = taskInstance.getPermissions()
                        .iterator();
                while (taskPermissions.hasNext()) {
                    if (acl.hasPermission((Permission) taskPermissions.next())) {
                        usersTasks.add(taskInstance);
                        break;
                    }
                }
            }

            return usersTasks;
        } catch (InitializationException e) {
            log.error("Failed to load users service", e);
            throw new NestableException(e);
        } catch (UnknownEntityException e) {
            log.error("User does not exist", e);
            throw new NestableException(e);
        } catch (HibernateException e) {
            log.error("Datastore problems building task list", e);
            throw new NestableException(e);
        }

    }

    /**
     * Get the task list for 
     * there use currently logged in according to the userLocator
     * @return
     * @throws NestableException
     */
    public List getTaskList() throws NestableException {
        return this.getTaskList(UserLocator.getLoggedInUser());
    }

    /**
     * Gets tasks for the current user that are owned by the current user
     * or no-one
     * @return
     * @throws NestableException
     */
    public List getOwnedTaskList() throws NestableException {
        //return this.getOwnerTaskList(UserLocator.getLoggedInUser());
        return this.getOwnerTaskList(UserLocator.getLoggedInUser());
    }

    /**
     * Screen to use when a task is completed sucessfully 
     * @return
     */
    public String getTaskListScreenName() {
        return "Index.vm";
    }

    /**
     * Returns the screen name as used in Exec function
     * @return
     */
    public String getTaskListScreen() {
        return "Index";
    }

    /**
     * Returns set of permissions for passed String
     * @param permissionsString as a ; seperated string
     * @return
     * @throws NestableException
     */
    public PermissionSet getPermissionSet(String permissionsString)
            throws NestableException {
        if (permissionsString != null) {
            String[] permissions = permissionsString.split(";");
            return getPermissionSet(permissions);
        } else {
            return new PermissionSet();
        }
    }

    /**
     * Gets a permission set for String[] of permission names
     * @param permissions
     * @return
     * @throws NestableException
     */
    public PermissionSet getPermissionSet(String[] permissions)
            throws NestableException {
        try {
            PermissionManager permissionManager = AvalonServiceHelper
                    .instance().getSecurityService().getPermissionManager();

            PermissionSet permissionSet = new PermissionSet();
            for (int i = 0; i < permissions.length; i++) {
                try {
                    permissionSet.add(permissionManager
                            .getPermissionByName(permissions[i]));
                } catch (UnknownEntityException e1) {
                    // Does not exist yet so create it
                    try {
                        Permission permission = permissionManager
                                .getPermissionInstance(permissions[i]);
                        permissionManager.addPermission(permission);
                        permissionSet.add(permission);
                    } catch (UnknownEntityException e) {
                        log.error("Cannot find permission", e);
                        throw new NestableException(e);
                    } catch (EntityExistsException e) {
                        log.error(
                                "Somehow the entity exists and does not exist",
                                e);
                        throw new NestableException(e);
                    }
                }
            }

            return permissionSet;
        } catch (InitializationException e) {
            log.error("Trying to initialize start permissions not possible", e);
            throw new NestableException(e);
        } catch (DataBackendException e) {
            log.error("Trying to initialize start permissions not possible", e);
            throw new NestableException(e);
        }
    }

    /**
     * loads a permission or creates it if it doesn't already exist. 
     * @param permissionName
     * @return
     * @throws InitializationException
     */
    public Permission loadOrCreatePermission(String permissionName)
            throws NestableException {

        try {
            PermissionManager permissionManager = AvalonServiceHelper
                    .instance().getSecurityService().getPermissionManager();

            Permission permission = permissionManager
                    .getPermissionInstance(permissionName);
            if (permissionManager.checkExists(permission)) {
                return permissionManager.getPermissionByName(permissionName);
            }
            permissionManager.addPermission(permission);
            return permission;
        } catch (DataBackendException e) {
            log.error("Failed to find or create permission:" + permissionName,
                    e);
            throw new NestableException(e);
        } catch (UnknownEntityException e) {
            log.error("Failed to find or create permission:" + permissionName,
                    e);
            throw new NestableException(e);
        } catch (InitializationException e) {
            log.error("Failed to find or create permission:" + permissionName,
                    e);
            throw new NestableException(e);
        } catch (EntityExistsException e) {
            log.error("Failed to find or create permission:" + permissionName,
                    e);
            throw new NestableException(e);
        }
    }

}