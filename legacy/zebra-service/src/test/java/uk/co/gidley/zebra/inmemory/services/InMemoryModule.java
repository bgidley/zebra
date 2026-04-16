/*
 * Original Code Copyright 2004, 2005 Anite - Central Government Division
 * http://www.anite.com/publicsector
 *
 * Modifications Copyright 2010 Ben Gidley
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

package uk.co.gidley.zebra.inmemory.services;

import com.anite.zebra.core.factory.api.IStateFactory;
import org.apache.tapestry5.ioc.ServiceBinder;
import org.apache.tapestry5.ioc.annotations.SubModule;
import uk.co.gidley.zebra.service.services.ProcessDefinitionFactory;
import uk.co.gidley.zebra.service.services.Zebra;
import uk.co.gidley.zebra.service.services.ZebraServiceModule;

/**
 * Created by IntelliJ IDEA. User: ben Date: Apr 15, 2010 Time: 7:04:20 PM
 */
@SubModule(ZebraServiceModule.class)
public class InMemoryModule {
    public static void bind(ServiceBinder binder) {
        binder.bind(InMemoryDatastore.class);
        binder.bind(ProcessDefinitionFactory.class, InMemoryProcessDefinitionFactory.class);
        binder.bind(IStateFactory.class,InMemoryStateFactory.class);
    }

}
