package com.anite.zebra.core.definitions;
/*
 * Copyright 2004/2005 Anite - Enforcement & Security
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
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.IRoutingDefinition;
import com.anite.zebra.core.definitions.api.IRoutingDefinitions;

public class MockRoutingDefs

implements IRoutingDefinitions {

	private final IProcessDefinition def;

	private Map routingDefs = new HashMap();

	/**
	 * @param def
	 */
	MockRoutingDefs(IProcessDefinition def) {
		this.def = def;
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see com.anite.zebra.impl.AbstractRoutingDefs#getProcessDef()
	 */
	public IProcessDefinition getProcessDef() {
		return def;
	}

	public void add(IRoutingDefinition routingDef) {
		routingDefs.put(routingDef.getId(), routingDef);
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see com.anite.zebra.core.definitions.api.IRoutingDefinitions#iterator()
	 */
	public Iterator iterator() {
		return routingDefs.values().iterator();
	}

	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @return
	 */
	public int size() {
		return routingDefs.size();
	}

	/**
	 * @author Matthew Norris
	 * Created on 19-Aug-2005
	 *
	 * @param mr
	 * @return
	 */
	public boolean contains(MockRouting mr) {
		return routingDefs.containsValue(mr);
	}
}