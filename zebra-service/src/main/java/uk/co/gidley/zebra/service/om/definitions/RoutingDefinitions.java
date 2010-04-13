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

package uk.co.gidley.zebra.service.om.definitions;

import com.anite.zebra.core.definitions.api.IRoutingDefinitions;

import java.util.Iterator;
import java.util.Set;

/**
 * @author Eric Pugh Routing definition is solely used to hide the set of routingDefintions from the user.  They get a
 *         routingDefinition that wraps the set.
 */
public class RoutingDefinitions implements IRoutingDefinitions {

	private Set routingDefinitions = null;

	private RoutingDefinitions() {

	}

	public RoutingDefinitions(Set routingDefinitions) {
		this.routingDefinitions = routingDefinitions;
	}

	public Iterator iterator() {
		return routingDefinitions.iterator();
	}
}