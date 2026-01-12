/*
 * Copyright 2004 Anite - Central Government Division
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

package com.anite.penguin.screenEndPoint.api;


/**
 * This service resolves the endpoint (e.g. action) for a given screen
 * Created May 12, 2004
 */
public interface ScreenEndPoint {
    public static final String ROLE="com.anite.penguin.screenEndPoint.api.ScreenEndPoint";
    
    /** 
     * Get the endpoint for the passed screen
     * Normally this is an action
     */
    public String getEndPoint(String screen);
}
