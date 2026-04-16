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

package com.anite.zebra.ext.definitions.api;

import java.util.Iterator;



/**
 * @author matt
 */
public interface IProperties {
	/**
	 * @return Returns the name.
	 */
	public String getName();
	public Object get(Object key);
	public String getString(String key);
	public Long getLongAsObj(String key);
	public long getLong(String key);
	public Integer getIntegerAsObj(String key);
	public int getInteger(String key);
	public Boolean getBooleanAsObj(String key);
	public boolean getBoolean(String key);
	public void put(String key, String value);
	public boolean containsKey(String key);
	public Iterator keys();
}