/*
 * Created on 10-Sep-2004
 */
package com.anite.antelope;

import junit.extensions.TestSetup;
import junit.framework.Test;
import junit.framework.TestSuite;

import com.anite.antelope.security.UserGroupPermissionsHelperT3st;
import com.anite.antelope.zebra.factory.TurbineAntelopeStateFactoryTest;
import com.anite.antelope.zebra.helper.TurbineAntelopeRunWorkflowTest;
import com.anite.antelope.zebra.helper.TurbineAntelopeWorkflowSubProcessTest;
import com.anite.antelope.zebra.helper.TurbineZebraHelperTest;
import com.anite.antelope.zebra.modules.actions.TurbineAntelopeActionletWorkFlowActionTest;
import com.anite.antelope.zebra.om.TurbineAntelopeFOETest;
import com.anite.antelope.zebra.om.TurbineAntelopeProcessDefinitionTest;
import com.anite.antelope.zebra.om.TurbineAntelopeProcessInstanceTest;
import com.anite.antelope.zebra.om.TurbineAntelopeProcessVersionsTest;
import com.anite.antelope.zebra.om.TurbineAntelopePropertyElementTest;
import com.anite.antelope.zebra.om.TurbineAntelopePropertyGroupsTest;
import com.anite.antelope.zebra.om.TurbineAntelopePropertySetEntryTest;
import com.anite.antelope.zebra.om.TurbineAntelopeRoutingDefinitionTest;
import com.anite.antelope.zebra.om.TurbineAntelopeTaskDefinitionTest;
import com.anite.antelope.zebra.om.TurbineAntelopeTaskInstanceHistoryTest;
import com.anite.antelope.zebra.om.TurbineAntelopeTaskInstanceTest;

/**
 * @author Ben.Gidley
 */
public class AllTurbineTests {

    public static Test suite() {
        TestSuite suite = new TestSuite("All Turbine Dependance Tests");

        suite.addTestSuite(TurbineAntelopeStateFactoryTest.class);
        suite.addTestSuite(TurbineAntelopeWorkflowSubProcessTest.class);
        suite.addTestSuite(TurbineAntelopeRunWorkflowTest.class);
        suite.addTestSuite(TurbineZebraHelperTest.class);
        suite.addTestSuite(TurbineAntelopeFOETest.class);
        suite.addTestSuite(TurbineAntelopeProcessDefinitionTest.class);
        suite.addTestSuite(TurbineAntelopeProcessInstanceTest.class);
        suite.addTestSuite(TurbineAntelopeProcessVersionsTest.class);
        suite.addTestSuite(TurbineAntelopePropertyElementTest.class);
        suite.addTestSuite(TurbineAntelopePropertyGroupsTest.class);
        suite.addTestSuite(TurbineAntelopePropertySetEntryTest.class);
        suite.addTestSuite(TurbineAntelopeRoutingDefinitionTest.class);
        suite.addTestSuite(TurbineAntelopeTaskDefinitionTest.class);
        suite.addTestSuite(TurbineAntelopeTaskInstanceTest.class);
        suite.addTestSuite(TurbineAntelopeTaskInstanceHistoryTest.class);
        suite.addTestSuite(TurbineAntelopeActionletWorkFlowActionTest.class);
        suite.addTestSuite(UserGroupPermissionsHelperT3st.class);
        
        TestSetup wrapper = new TestSetup(suite){
            
            protected void setUp() {
                oneTimeSetUp();
            }

            protected void tearDown() {
                oneTimeTearDown();
            }
            
        };
        
        return wrapper;
    }
    
    public static void oneTimeSetUp() {
        TurbineTestCase.initialiseTurbine();
    }

    public static void oneTimeTearDown() {

    }
}
