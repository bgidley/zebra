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

import javax.persistence.Entity;
import javax.persistence.Transient;

/**
 * Represents a time of day to the nearest minute 
 * @author Mike Jones
 *
 */
@Entity
public class Time extends BaseDomain {

    private String name;
    
    private Integer hour;
    private Integer minute;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

	public Integer getHour() {
		return hour;
	}

	public void setHour(Integer hour) {
		this.hour = hour;
	}

	public Integer getMinute() {
		return minute;
	}

	public void setMinute(Integer minute) {
		this.minute = minute;
	}
    
	/**
	 * Provide the job name to represent this time
	 * @return
	 */
	@Transient
    public String getJobName(){
		StringBuffer name = new StringBuffer();
		
		if (hour < 10){
			name.append("0");						
		} 
		name.append(hour);
		name.append(":");
		if (minute < 10){
			name.append("0");
		}
		name.append(minute);
		
		return name.toString();
	}

}
