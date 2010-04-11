package org.apache.fulcrum.security;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;

public class AbstractSecurityServiceTest extends TestCase {

    private SecurityService securityService;
    private UserManager userManager;
    private ModelManager modelManager;
    private GroupManager groupManager;
    private RoleManager roleManager;
    private PermissionManager permissionManager;
    
    
    public GroupManager getGroupManager() {
        return groupManager;
    }

    public void setGroupManager(GroupManager groupManager) {
        this.groupManager = groupManager;
    }

    public ModelManager getModelManager() {
        return modelManager;
    }

    public void setModelManager(ModelManager modelManager) {
        this.modelManager = modelManager;
    }

    public RoleManager getRoleManager() {
        return roleManager;
    }

    public void setRoleManager(RoleManager roleManager) {
        this.roleManager = roleManager;
    }

    public UserManager getUserManager() {
        return userManager;
    }

    public void setUserManager(UserManager userManager) {
        this.userManager = userManager;
    }

    public void setUp() throws Exception{
        securityService = (SecurityService) RegistryManager.getInstance().getRegistry().getService(SecurityService.class);
        userManager = securityService.getUserManager();
        groupManager = securityService.getGroupManager();
        roleManager = securityService.getRoleManager();
        modelManager = securityService.getModelManager();
        permissionManager = securityService.getPermissionManager();
    }

    public SecurityService getSecurityService() {
        return securityService;
    }

    public void setSecurityService(SecurityService securityService) {
        this.securityService = securityService;
    }

    public PermissionManager getPermissionManager() {
        return permissionManager;
    }

    public void setPermissionManager(PermissionManager permissionManager) {
        this.permissionManager = permissionManager;
    }
}
