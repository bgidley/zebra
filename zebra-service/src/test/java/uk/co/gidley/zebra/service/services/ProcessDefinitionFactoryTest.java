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
package uk.co.gidley.zebra.service.services;

import com.sun.org.apache.xalan.internal.xsltc.ProcessorVersion;
import org.testng.annotations.Test;
import uk.co.gidley.zebra.inmemory.services.InMemoryDatastore;
import uk.co.gidley.zebra.service.om.definitions.ProcessDefinition;
import uk.co.gidley.zebra.service.om.definitions.ProcessVersion;

import java.util.HashSet;

import static org.hamcrest.MatcherAssert.*;
import static org.hamcrest.Matchers.*;

public class ProcessDefinitionFactoryTest extends IocBaseTest {

    public void beforeTest(){
        InMemoryDatastore inMemoryDatastore = registry.getService(InMemoryDatastore.class);
        inMemoryDatastore.getProcessVersions();

        ProcessVersion processVersions = new ProcessVersion();
        processVersions.setId(getNextId());
        processVersions.setName("PDFTestProcess1");
        processVersions.setProcessVersions(new HashSet<ProcessDefinition>());

        ProcessDefinition processDefinition = new ProcessDefinition();
        processDefinition.setId(getNextId());
        processDefinition.setProcessVersions(processVersions);
        processVersions.getProcessVersions().add(processDefinition);
        

    }

    private long getNextId() {
        return 1L;
    }

    @Test
    public void testProcessDefintionFactory() {

        ProcessDefinitionFactory processDefinitionFactory = registry.getService(ProcessDefinitionFactory.class);
        assertThat(processDefinitionFactory, notNullValue());


    }


}
