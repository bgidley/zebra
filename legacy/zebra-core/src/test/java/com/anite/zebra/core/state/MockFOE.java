package com.anite.zebra.core.state;
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
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;

/**
 * Mock FOE class
 * 
 * @author Matthew Norris
 * @author Eric Pugh
 *
 */
public class MockFOE implements IFOE {
	private static long counter = 0;
	private Long foeID = null;
	private IProcessInstance processInstance;
	/**
	 * default constructor; must supply a valid process instance
	 * 
	 * @param processInstance
	 *
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	public MockFOE(IProcessInstance processInstance) {
		this.foeID = new Long(counter++);
		this.processInstance = processInstance;
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.state.api.IFOE#getProcessInstance()
	 */
	public IProcessInstance getProcessInstance() {
		return processInstance;
	}

	/**
	 * @return Returns the foeID.
	 *
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	public Long getFoeID() {
		return foeID;
	}

	/**
	 * @return Returns a counter representing the total 
	 * 		   number of these objects constructed.
	 * @author Matthew.Norris
	 * Created on Sep 25, 2005
	 */
	public static long getCounter() {
		return counter;
	}

	/* (non-Javadoc)
	 * @see java.lang.Object#toString()
	 */
	public String toString() {
		return "MOCKFOE - " + foeID;
	}

}
