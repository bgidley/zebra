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

package com.anite.antelope.zebra.modules.actions;

import junit.framework.TestCase;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.zebra.modules.actionlet.Actionlet;
import com.anite.penguin.form.Field;
import com.anite.penguin.form.MissingField;
import com.anite.penguin.modules.tools.FieldMap;
import com.anite.penguin.modules.tools.FormTool;

/**
 * 
 * @author Michael.Jones
 */
public class TurbineAntelopeActionletWorkFlowActionTest extends TestCase {

    ActionletWorkflowAction actionletWorkflowAction;

    FormTool form;

    /* (non-Javadoc)
     * @see junit.framework.TestCase#setUp()
     */
    protected void setUp() throws Exception {
        form = new FormTool();
        // Initialise Fake Turbine so it can resolve Avalon
        TurbineTestCase.initialiseTurbine();

        actionletWorkflowAction = new TestImpl();

        // create a rang of fields to test
        FieldMap fields = new FieldMap();

        Field field = new MissingField();
        field.setName("missingfield");
        fields.put(field.getName(), field);

        field = new Field();
        field.setName("fieldwithnovlaue");
        fields.put(field.getName(), field);

        field = new Field();
        field.setValue("fieldwithvalue");
        field.setName("fieldwithvalue");
        fields.put(field.getName(), field);

        field = new Field();
        field.setValue("");
        field.setName("mutliple[0]");
        fields.put(field.getName(), field);

        field = new Field();
        field.setValue("trigger");
        field.setName("mutlipletrigger[0]");
        fields.put(field.getName(), field);

        form.setFields(fields);

    }

    /*
     * simple checks to see if the fields come though as triggers if they contain values 
     *
     */
    public void testContainsActiveTrigger() {
        // a missing field should NOT trigger
        assertFalse(actionletWorkflowAction.containsActiveTrigger(form,
                "missingField"));
        // a field with no value should NOT trigger
        assertFalse(actionletWorkflowAction.containsActiveTrigger(form,
                "fieldwithnovlaue"));

        assertFalse(actionletWorkflowAction.containsActiveTrigger(form,
                "mutliple"));

        // a field with a value SHOULD trigger
        assertTrue(actionletWorkflowAction.containsActiveTrigger(form,
                "fieldwithvalue"));
        assertTrue(actionletWorkflowAction.containsActiveTrigger(form,
                "mutlipletrigger"));

    }

    /*
     * check that a mutlip field witha value does trigger a differnt 
     * value
     * 
     */
    public void testContainsActiveTriggerSameName() {
        Field field = new Field();
        field.setName("prefix[1]");
        field.setValue("prefix");
        form.getFields().put(field.getName(), field);

        field = new Field();
        field.setName("prefixend");
        form.getFields().put(field.getName(), field);

        assertTrue(actionletWorkflowAction
                .containsActiveTrigger(form, "prefix"));
        assertFalse(actionletWorkflowAction.containsActiveTrigger(form,
                "prefixend"));

    }

    /**
     * innser class just for this test
     * 
     * @author Michael.Jones
     */
    class TestImpl extends ActionletWorkflowAction {

        /* (non-Javadoc)
         * @see com.anite.antelope.zebra.modules.actions.ActionletWorkflowAction#getActionLets()
         */
        public Actionlet[] getActionLets() {
            // TODO Auto-generated method stub
            return null;
        }

    }

}