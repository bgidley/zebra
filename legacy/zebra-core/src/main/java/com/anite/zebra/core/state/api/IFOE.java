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

package com.anite.zebra.core.state.api;

/**
 * 
 * Flow of Execution interface declaration. 
 * 
 * This object does nothing for the engine itself, and is more of a helper for the outside world.
 * 
 * Every task instance runs within a FOE.
 * 
 * Tasks created from SERIAL routings execute within the same FOE as the initiating task, with the
 * single exception of when the initiating task is a Sync task.
 *  
 * Tasks created from PARALLEL routings run on a new FOE for each routing, regardless of 
 * the Sync flag on the initiating task.
 * 
 * When a Sync executes, a new FOE is created (as potentially several FOEs are being synced together) 
 * and any SERIAL tasks immdiately after it run within this new FOE.
 * 
 * What use is a FOE to me?
 * 
 * In parallel situations it is desirable to have run-time / dynamic properties that are unique to 
 * this thread of execution. Without the FOE it would only be possible to tell which Process this was being run on.
 * 
 * The FOE is also useful for audit trails as it gives an indication of the full flow of execution through the process.  
 * 
 * 
 * @author Matthew.Norris
 * 
 */

public interface IFOE extends IStateObject {
	/**
	 * Process Instance this FOE belongs to
	 * @return
	 */
	public IProcessInstance getProcessInstance();
	
}
