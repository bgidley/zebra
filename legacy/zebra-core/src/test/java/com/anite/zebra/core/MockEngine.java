/*
 * Copyright 2005 Anite - Enforcement & Security
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

package com.anite.zebra.core;

import com.anite.zebra.core.factory.api.IClassFactory;
import com.anite.zebra.core.factory.api.IStateFactory;

/**
 * @author Matthew.Norris
 * Created on 22-Sep-2005
 */
public class MockEngine extends Engine {

	private String engineName;
	
	/**
	 * @param stateFactory
	 * @param classFactory
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public MockEngine(IStateFactory stateFactory, IClassFactory classFactory) {
		super(stateFactory, classFactory);
		// TODO Auto-generated constructor stub
	}

	/**
	 * @param stateFactory
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public MockEngine(IStateFactory stateFactory) {
		super(stateFactory);
		// TODO Auto-generated constructor stub
	}

	/**
	 * @return Returns the engineName.
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public String getEngineName() {
		return engineName;
	}

	/**
	 * @param engineName The engineName to set.
	 *
	 * @author Matthew.Norris
	 * Created on 22-Sep-2005
	 */
	public void setEngineName(String engineName) {
		this.engineName = engineName;
	}

}
