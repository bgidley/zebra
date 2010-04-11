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
package com.anite.zebra.avalon.impl;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;
import com.anite.zebra.core.state.api.IStateObject;
import com.anite.zebra.core.state.api.ITaskInstance;
import com.anite.zebra.core.state.api.ITransaction;

/**
 * @author Eric Pugh
 *
 */
public class MockStateFactory implements IStateFactory {

    /**
     * 
     */
    public MockStateFactory() {
        super();
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#beginTransaction()
     */
    public ITransaction beginTransaction() throws StateFailureException {
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#saveObject(com.anite.zebra.core.state.api.IStateObject)
     */
    public void saveObject(IStateObject arg0) throws StateFailureException {

    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#deleteObject(com.anite.zebra.core.state.api.IStateObject)
     */
    public void deleteObject(IStateObject arg0) throws StateFailureException {

    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#createProcessInstance(com.anite.zebra.core.definitions.api.IProcessDefinition)
     */
    public IProcessInstance createProcessInstance(IProcessDefinition arg0) throws CreateObjectException {
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#createTaskInstance(com.anite.zebra.core.definitions.api.ITaskDefinition, com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.state.api.IFOE)
     */
    public ITaskInstance createTaskInstance(ITaskDefinition arg0, IProcessInstance arg1, IFOE arg2)
            throws CreateObjectException {
        return null;
    }

    /* (non-Javadoc)
     * @see com.anite.zebra.core.factory.api.IStateFactory#createFOE(com.anite.zebra.core.state.api.IProcessInstance)
     */
    public IFOE createFOE(IProcessInstance arg0) throws CreateObjectException {
        return null;
    }

	public void acquireLock(IProcessInstance arg0) throws LockException {
		// TODO Auto-generated method stub
		
	}

	public void releaseLock(IProcessInstance arg0) throws LockException {
		// TODO Auto-generated method stub
		
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#acquireLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
	 */
	public void acquireLock(IProcessInstance arg0, IEngine arg1) throws LockException {
		// TODO Auto-generated method stub
		
	}

	/* (non-Javadoc)
	 * @see com.anite.zebra.core.factory.api.IStateFactory#releaseLock(com.anite.zebra.core.state.api.IProcessInstance, com.anite.zebra.core.api.IEngine)
	 */
	public void releaseLock(IProcessInstance arg0, IEngine arg1) throws LockException {
		// TODO Auto-generated method stub
		
	}

}
