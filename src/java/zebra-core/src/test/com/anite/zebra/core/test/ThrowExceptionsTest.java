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

package com.anite.zebra.core.test;

import junit.framework.TestCase;

import com.anite.zebra.core.Engine;
import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.processdef.ClassExceptionProcess;
import com.anite.zebra.core.exceptions.CreateProcessException;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.factory.CachedClassFactory;
import com.anite.zebra.core.factory.MockStateFactory;
import com.anite.zebra.core.state.MockProcessInstance;

/**
 * tests to ensure exceptions are being thrown
 * 
 * @author Matthew.Norris
 * Created on Aug 21, 2005
 */
public class ThrowExceptionsTest extends TestCase {

	public void testThrowExceptions()throws Exception {
		ClassExceptionProcess pd = new ClassExceptionProcess("testThrowExceptions");
		CachedClassFactory ccf = new CachedClassFactory();
		MockStateFactory msf = new MockStateFactory();
		IEngine eng = new Engine(msf,ccf);
		
		// start and run once to prove it works
		MockProcessInstance pi = (MockProcessInstance) eng.createProcess(pd);
		eng.startProcess(pi);
		// make routing invalid and try again
		pd = new ClassExceptionProcess("testFailRouting");
		pd.failConditionAction=true;
		runFailTest(eng,pd);		
		
		// make taskconstruct invalid and try again
		pd = new ClassExceptionProcess("testFailTaskConstruct");
		pd.failTaskConstruct=true;
		runFailTest(eng,pd);		
		
		// make taskaction invalid and try again
		pd = new ClassExceptionProcess("testFailTaskAction");
		pd.failTaskAction=true;
		runFailTest(eng,pd);		
		
		// make processConstruct invalid and try again
		pd = new ClassExceptionProcess("testFailProcessConstruct");
		pd.failProcessConstruct=true;
		runFailTest(eng,pd);		

		// make processDestruct invalid and try again
		pd = new ClassExceptionProcess("testFailProcessDestruct");
		pd.failProcessDestruct = true;
		runFailTest(eng,pd);		

	}
	private void runFailTest(IEngine eng, IProcessDefinition pd) throws CreateProcessException {
		MockProcessInstance pi = (MockProcessInstance) eng.createProcess(pd);
		Exception caught=null;
		try {
			eng.startProcess(pi);
		} catch (StartProcessException e) {
			caught = e;
		}
		assertNotNull(caught);

	}

}
