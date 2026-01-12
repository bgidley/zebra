/*
 * Copyright 2004, 2005 Anite 
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
package com.anite.zebra.hivemind.om.timedtask;

import java.util.Date;

import javax.persistence.ManyToOne;
import javax.persistence.MappedSuperclass;

import com.anite.zebra.hivemind.om.timedtask.BaseDomain;
import com.anite.zebra.hivemind.om.timedtask.Time;

@MappedSuperclass
public class AbstractTimedTask extends BaseDomain {
	private Time time;
	
	private Date runTaskDate;

	private Long zebraTaskInstanceId;

	@ManyToOne
	public Time getTime() {
		return time;
	}

	public void setTime(Time time) {
		this.time = time;
	}

	public Long getZebraTaskInstanceId() {
		return zebraTaskInstanceId;
	}

	public void setZebraTaskInstanceId(Long zebraTaskInstanceId) {
		this.zebraTaskInstanceId = zebraTaskInstanceId;
	}

	public Date getRunTaskDate() {
		return runTaskDate;
	}

	public void setRunTaskDate(Date runTaskDate) {
		this.runTaskDate = runTaskDate;
	}
}
