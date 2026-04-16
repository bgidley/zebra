/*
 * Copyright 2004/2005 Anite - Enforcement & Security
 * http://www.anite.com/publicsector
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
package com.anite.zebra.core.state.api;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
/**
 * @author Matthew.Norris
 * 
 * Basic state transaction interface.
 * 
 * NOTE: It is currently *assumed* by the Engine that a Transaction that is not
 * explicitly commited is automatically rolled-back by the transaction provider.
 * You have been warned!
 *  
 */
public interface ITransaction {
	/**
	 * commit this transaction
	 * 
	 * @throws StateFailureException
	 */
	public void commit() throws StateFailureException;
	/**
	 * rollback this transaction
	 * 
	 * @throws StateFailureException
	 */
	public void rollback() throws StateFailureException;
}