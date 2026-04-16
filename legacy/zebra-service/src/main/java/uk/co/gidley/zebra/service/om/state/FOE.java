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

package uk.co.gidley.zebra.service.om.state;

import com.anite.zebra.core.state.api.IFOE;
import com.anite.zebra.core.state.api.IProcessInstance;

import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.ManyToOne;

/**
 * @author Ben.Gidley
 */
@Entity
public class FOE implements IFOE {

	private ProcessInstance processInstance;

	private Integer id;

	public FOE() {
		// noop
	}

	/**
	 * @param processInstance
	 */
	public FOE(ProcessInstance processInstance) {
		this.processInstance = (ProcessInstance) processInstance;
		this.processInstance.getFOEs().add(this);
	}

	@ManyToOne(targetEntity = ProcessInstance.class)
	public IProcessInstance getProcessInstance() {
		return this.processInstance;
	}

	/**
	 * @param processInstance The processInstance to set.
	 */
	public void setProcessInstance(ProcessInstance processInstance) {
		this.processInstance = (ProcessInstance) processInstance;
	}

	@Id
	@GeneratedValue
	public Integer getId() {
		return this.id;
	}

	public void setId(Integer id) {
		this.id = id;
	}

}