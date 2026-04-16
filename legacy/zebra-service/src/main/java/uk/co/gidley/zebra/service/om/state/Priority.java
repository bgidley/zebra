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

import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;

/**
 * @author Ben Gidley
 */
@Entity
public class Priority {

	private Long priorityId;

	private String caption;

	private Integer sortKey;

	public String getCaption() {
		return this.caption;
	}

	public void setCaption(String caption) {
		this.caption = caption;
	}

	public Integer getSortKey() {
		return this.sortKey;
	}

	public void setSortKey(Integer sortKey) {
		this.sortKey = sortKey;
	}

	@Id
	@GeneratedValue
	public Long getPriorityId() {
		return this.priorityId;
	}

	public void setPriorityId(Long priorityId) {
		this.priorityId = priorityId;
	}
}
