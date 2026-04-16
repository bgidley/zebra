package com.anite.zebra.hivemind.impl;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import org.apache.commons.lang.NotImplementedException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.lang.exception.NestableRuntimeException;
import org.apache.commons.logging.Log;
import org.apache.fulcrum.security.PermissionManager;
import org.apache.fulcrum.security.UserManager;
import org.apache.fulcrum.security.entity.Permission;
import org.apache.fulcrum.security.hibernate.dynamic.model.HibernateDynamicUser;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.EntityDisabledException;
import org.apache.fulcrum.security.util.EntityExistsException;
import org.apache.fulcrum.security.util.PermissionSet;
import org.apache.fulcrum.security.util.UnknownEntityException;
import org.hibernate.Query;
import org.hibernate.Session;

import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;
import com.anite.zebra.hivemind.util.RegistryHelper;

/**
 * A service to help Zebra Manager its link to the Permission Service
 * @author ben.gidley
 *
 */
public class ZebraSecurity {

    private Log log;

    private PermissionManager permissionManager;

    private UserManager userManager;

    /**
     * Returns set of permissions for passed String
     * 
     * @param permissionsString
     *            as a ; seperated string
     * @return
     * @throws NestableException
     */
    public PermissionSet getPermissionSet(String permissionsString) {
        if (permissionsString != null) {
            String[] permissions = permissionsString.split(";");
            return getPermissionSet(permissions);
        } else {
            return new PermissionSet();
        }
    }

    /**
     * Gets a permission set for String[] of permission names
     * 
     * @param permissions
     * @return
     * @throws NestableException
     */
    public PermissionSet getPermissionSet(String[] permissions) {
        try {

            PermissionSet permissionSet = new PermissionSet();
            for (int i = 0; i < permissions.length; i++) {
                try {
                    permissionSet.add(this.permissionManager.getPermissionByName(permissions[i]));
                } catch (UnknownEntityException e1) {
                    // Does not exist yet so create it
                    try {
                        Permission permission = this.permissionManager.getPermissionInstance(permissions[i]);
                        this.permissionManager.addPermission(permission);
                        permissionSet.add(permission);
                    } catch (UnknownEntityException e) {
                        this.log.error("Cannot find permission", e);
                        throw new NestableRuntimeException(e);
                    } catch (EntityExistsException e) {
                        this.log.error("Somehow the entity exists and does not exist", e);
                        throw new NestableRuntimeException(e);
                    }
                } catch (EntityDisabledException e) {
                    log.error("Error getting permission set:", e);
                }
            }

            return permissionSet;

        } catch (DataBackendException e) {
            this.log.error("Trying to initialize start permissions not possible", e);
            throw new NestableRuntimeException(e);
        }
    }

    /**
     * loads a permission or creates it if it doesn't already exist.
     * 
     * @param permissionName
     * @return
     * @throws InitializationException
     */
    public Permission loadOrCreatePermission(String permissionName) {

        try {

            Permission permission = this.permissionManager.getPermissionInstance(permissionName);
            if (this.permissionManager.checkExists(permission)) {
                return this.permissionManager.getPermissionByName(permissionName);
            }
            this.permissionManager.addPermission(permission);
            return permission;
        } catch (EntityDisabledException e) {
            this.log.error("Failed to find or create permission:" + permissionName, e);
            throw new NestableRuntimeException(e);
        } catch (DataBackendException e) {
            this.log.error("Failed to find or create permission:" + permissionName, e);
            throw new NestableRuntimeException(e);
        } catch (UnknownEntityException e) {
            this.log.error("Failed to find or create permission:" + permissionName, e);
            throw new NestableRuntimeException(e);

        } catch (EntityExistsException e) {
            this.log.error("Failed to find or create permission:" + permissionName, e);
            throw new NestableRuntimeException(e);
        }
    }

    public PermissionManager getPermissionManager() {
        return this.permissionManager;
    }

    public void setPermissionManager(PermissionManager permissionManager) {
        this.permissionManager = permissionManager;
    }

    public void setLog(Log log) {
        this.log = log;
    }

    /**
     * Get a task list for the passed user
     * @param user
     * @return
     */
    public List<ZebraTaskInstance> getTaskList(DynamicUser user) {

        try {
            Session session = RegistryHelper.getInstance().getSession();
            Query tasks = session
                    .createQuery("from ZebraTaskInstance ati where (ati.taskOwner = :user or ati.taskOwner is null) and ati.showInTaskList = :show");
            tasks.setBoolean("show", true);
            tasks.setEntity("user", user);

            tasks.setCacheable(true);

            List<ZebraTaskInstance> usersTasks = new ArrayList<ZebraTaskInstance>();

            DynamicAccessControlList acl = (DynamicAccessControlList) userManager.getACL(user);

            Iterator allTasks = tasks.iterate();
            while (allTasks.hasNext()) {
                ZebraTaskInstance taskInstance = (ZebraTaskInstance) allTasks.next();
                Iterator taskPermissions = taskInstance.getPermissions().iterator();
                while (taskPermissions.hasNext()) {
                    if (acl.hasPermission((Permission) taskPermissions.next())) {
                        usersTasks.add(taskInstance);
                        break;
                    }
                }
            }

            return usersTasks;

        } catch (UnknownEntityException e) {
            throw new NestableRuntimeException(e);
        }

    }

    public List<ZebraTaskInstance> getOnlyOwnedTaskList(HibernateDynamicUser user) {
        throw new NotImplementedException("See Antelope for how to implement");
    }

    public List<ZebraTaskInstance> getOnlyDelegatedTaskList(HibernateDynamicUser user) {
        throw new NotImplementedException("See Antelope for how to implement");
    }

    public UserManager getUserManager() {
        return userManager;
    }

    public void setUserManager(UserManager userManager) {
        this.userManager = userManager;
    }
}
