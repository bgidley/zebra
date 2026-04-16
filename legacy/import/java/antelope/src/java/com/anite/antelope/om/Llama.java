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
 * @author Ben Gidley
 * @hibernate.joined-subclass
 * @hibernate.joined-subclass-key column="animalId"
 */
public class Llama extends Animal
{
    private int hairLength;
    /**
     * @hibernate.property
     * @return Returns the hairLength.
     */
    public int getHairLength() {
        return hairLength;
    }
    /**
     * @param hairLength The hairLength to set.
     */
    public void setHairLength(int hairLength) {
        this.hairLength = hairLength;
    }
    /* (non-Javadoc)
     * @see com.anite.antelope.om.Animal#getType()
     */
    public String getType() {
        return "Llama";
    }
    /* (non-Javadoc)
     * @see com.anite.antelope.om.Animal#getImage()
     */
    public String getImage() {
        return "images/llama.gif";
    }
}
