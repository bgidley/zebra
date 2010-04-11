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
package com.anite.zebra.ext.definitions.api;

/**
 * Simple process versioning api.
 * @author Matthew.Norris
 * @author michael.jones 
 */
public interface IProcessVersion {

    /**
     * Process Version Number
     * 
     * @return
     */
    public Long getVersion();

    /**
     * 
     * @param version
     */
    public void setVersion(Long version);

    /**
     * 
     * @return
     */
    public IProcessVersions getProcessVersions();

    /**
     * 
     * @param iProcessVersions
     */
    public void setProcessVersions(IProcessVersions iProcessVersions);

}