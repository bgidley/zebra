package org.apache.fulcrum.security.model;

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

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.apache.fulcrum.security.acl.AccessControlList;
import org.apache.fulcrum.security.model.dynamic.DynamicAccessControlList;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicPermission;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;

/**
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: ACLFactoryTest.java,v 1.3 2006/01/17 09:17:24 biggus_richus Exp $
 */
public class ACLFactoryTest extends TestCase {

    public void testCreatingDynamicACL() throws Exception {

        ACLFactory factory = (ACLFactory) RegistryManager.getInstance().getRegistry().getService(
                "fulcrum.security.aclFactoryDynamic", ACLFactory.class);
        DynamicUser user = new DynamicUser();
        user.setName("bob");
        user.setId(new Integer(1));
        DynamicGroup group = new DynamicGroup();
        group.setName("group1");
        group.setId(new Integer(1));
        DynamicRole role = new DynamicRole();
        role.setName("role1");
        role.setId(new Integer(1));
        DynamicPermission permission = new DynamicPermission();
        permission.setName("permission1");
        permission.setId(new Integer(1));
        role.addPermission(permission);
        group.addRole(role);
        user.addGroup(group);
        AccessControlList acl = factory.getAccessControlList(user);
        assertTrue(acl instanceof DynamicAccessControlList);
        DynamicAccessControlList dacl = (DynamicAccessControlList) acl;
        assertTrue(dacl.hasPermission(permission));
    }
}
