/*
 * Copyright 2010 Ben Gidley
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
package uk.co.gidley.inmemory.services;

import org.apache.tapestry5.ioc.Registry;
import org.apache.tapestry5.ioc.RegistryBuilder;
import org.testng.annotations.AfterSuite;
import org.testng.annotations.BeforeSuite;
import org.testng.annotations.Test;
import uk.co.gidley.zebra.inmemory.services.InMemoryModule;
import uk.co.gidley.zebra.service.services.Zebra;

import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.*;

public class InMemoryProcessTest {

    Registry registry;

    @BeforeSuite
    public void beforeSuite() {

        RegistryBuilder builder = new RegistryBuilder();
        builder.add(InMemoryModule.class);
        Registry registry = builder.build();
        registry.performRegistryStartup();
        this.registry = registry;
    }

    @AfterSuite
    public void afterSuite() {
        if (registry != null) {
            registry.shutdown();
        }
    }

    @Test
    public void testBasicWorkflow() {
        Zebra zebra = registry.getService(Zebra.class);
        assertThat(zebra, notNullValue());
    }


}
