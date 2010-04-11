/*
 * Copyright 2004 Anite - Central Government Division
 * http://www.aniteps.com
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

package com.anite.antelope.om;

/**
 * This represents a animal
 * @hibernate.class
 * @hibernate.query name="ownedAnimals" query="from Animal a where a.ownerLoginName = :ownerName"
 * Created 13-May-2004
 */
public abstract class Animal extends Active {

    private Integer animalId;

    private String name;

    private int age;

    private String ownerLoginName;

    /**
     * @hibernate.property
     * @return Returns the age.
     */
    public int getAge() {
        return age;
    }

    /**
     * @param age
     *            The age to set.
     */
    public void setAge(int age) {
        this.age = age;
    }

    /**
     * @hibernate.property
     * @return Returns the name.
     */
    public String getName() {
        return name;
    }

    /**
     * @param name
     *            The name to set.
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * @hibernate.id generator-class="native"
     * @return Returns the animalId.
     */
    public Integer getAnimalId() {
        return animalId;
    }

    /**
     * @param animalId
     *            The animalId to set.
     */
    public void setAnimalId(Integer animalId) {
        this.animalId = animalId;
    }

    /**
     * A string to describe this animal
     * 
     * @return
     */
    public abstract String getType();

    /**
     * The image for this animal
     * 
     * @return
     */
    public abstract String getImage();

    /**
     * @hibernate.property
     * @return Returns the ownerLoginName.
     */
    public String getOwnerLoginName() {
        return ownerLoginName;
    }

    /**
     * @param ownerLoginName
     *            The ownerLoginName to set.
     */
    public void setOwnerLoginName(String ownerLoginName) {
        this.ownerLoginName = ownerLoginName;
    }
}