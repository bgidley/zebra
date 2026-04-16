/*
 * Copyright 2004 Anite - Central Government Division
 *    http://www.aniteps.com
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

package com.anite.antelope.om;


/**
 * A moorhen is a bird with very long legs
 * @author Ben
 * @hibernate.joined-subclass
 * @hibernate.joined-subclass-key column="animalId"
 */
public class Moorhen extends Animal{

    private int legLength;

    /**
     * @hibernate.property
     * 
     * @return Returns the legLength.
     */
    public int getLegLength() {
        return legLength;
    }
    /**
     * @param legLength The legLength to set.
     */
    public void setLegLength(int legLength) {
        this.legLength = legLength;
    }
    /* (non-Javadoc)
     * @see com.anite.antelope.om.Animal#getType()
     */
    public String getType() {        
        return "Moorhen";
    }
    /* (non-Javadoc)
     * @see com.anite.antelope.om.Animal#getImage()
     */
    public String getImage() {
       
        return "images/moorhen.gif";
    }
}
