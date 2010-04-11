/*
 * Created on 10-Feb-2005
 */
package com.anite.antelope.zebra.helper;

import java.util.Iterator;

import junit.framework.TestCase;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;

import org.apache.avalon.framework.component.ComponentException;
import org.apache.commons.lang.exception.NestableException;
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

import com.anite.antelope.TurbineTestCase;
import com.anite.antelope.session.UserLocator;
import com.anite.antelope.zebra.om.AntelopeProcessInstance;
import com.anite.antelope.zebra.om.AntelopePropertySetEntry;
import com.anite.antelope.zebra.om.AntelopeTaskDefinition;
import com.anite.antelope.zebra.om.AntelopeTaskInstance;
import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;
import com.anite.zebra.core.exceptions.StartProcessException;
import com.anite.zebra.core.exceptions.TransitionException;

/**
 * @author Ben.Gidley
 */
public class TurbineAntelopeRunSubflowSpeedTest extends TestCase {

    private static final String OUTPUT3 = "3output";

    private static final String OUTPUT2 = "2output";

    private static final String INPUT3 = "3input";

    private static final String STOP3 = "Stop3";

    private static final String STOP2 = "Stop2";

    private static final String INPUT2 = "2input";

    private static final String START = "Start";

    private final static Log log = LogFactory
            .getLog(TurbineAntelopeRunSubflowSpeedTest.class);

    protected void setUp() throws Exception {

        TurbineTestCase.initialiseTurbine();
    }

    public void testRunSubflowSpeed() throws Exception {
        log.info("Running without objects");
        long start = System.currentTimeMillis();
        long current = start;
        for (int i = 0; i < 100; i++) {
            runWorkflowNoObjects();
            log.info("Flow " + i + " complated: in: "
                    + (System.currentTimeMillis() - current));
            current = System.currentTimeMillis();
        }
        long total = System.currentTimeMillis() - start;
        log.info("100 runs completed in : " + total);
        log.info("Average is: " + total / 5);
    }

    public void testRunSubflowSpeedObjects() throws Exception {

        log.info("Running with objects");
        Byte[] bytes = new Byte[100];
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] = new Byte("123");
        }

        long start = System.currentTimeMillis();
        long current = start;
        for (int i = 0; i < 100; i++) {
            runWorkflowWithObjects(bytes);
            log.info("Flow " + i + " complated: in: "
                    + (System.currentTimeMillis() - current));
            current = System.currentTimeMillis();
        }
        long total = System.currentTimeMillis() - start;
        log.info("100 runs completed in : " + total);
        log.info("Average is: " + total / 5);
    }

    /**
     * @param bytes
     * @throws NestableException
     * @throws StartProcessException
     * @throws ComponentException
     * @throws TransitionException
     * @throws PersistenceException
     * @throws HibernateException
     */
    private void runWorkflowWithObjects(Byte[] bytes) throws NestableException,
            StartProcessException, ComponentException, TransitionException,
            PersistenceException, HibernateException {
        log.debug("testing workflow Subprocess");

        AntelopeProcessInstance processInstance = ZebraHelper.getInstance()
                .createProcessPaused("TopLevel");
        assertNotNull(processInstance);

        log.debug("Starting Transition");
        long start = System.currentTimeMillis();
        AntelopePropertySetEntry input2Create = new AntelopePropertySetEntry(
                INPUT2);
        input2Create.setObject(bytes);
        processInstance.getPropertySet().put(INPUT2, input2Create);
        ZebraHelper.getInstance().getEngine().startProcess(processInstance);

        // Should run to stop2 on the child
        AntelopeTaskInstance stop2 = checkTaskDef(STOP2,
                (AntelopeProcessInstance) processInstance
                        .getAllChildProcesses().get(0));
        AntelopeProcessInstance middleProcess = stop2
                .getAntelopeProcessInstance();
        long duration = System.currentTimeMillis() - start;
        log.debug("Computed stop 2 in:" + duration);

        Session s = PersistenceLocator.getInstance().getCurrentSession();
        Transaction t = s.beginTransaction();

        // now check passing up/down
        AntelopePropertySetEntry input2 = (AntelopePropertySetEntry) middleProcess
                .getPropertySet().get(INPUT2);
        assertTrue(input2.getValue().equals(INPUT2));
        assertEquals(input2.getObject(), bytes);

        AntelopePropertySetEntry input3 = new AntelopePropertySetEntry();
        input3.setValue(INPUT3);
        input3.setObject(bytes);
        middleProcess.getPropertySet().put(INPUT3, input3);

        AntelopePropertySetEntry output2 = new AntelopePropertySetEntry();
        output2.setValue(OUTPUT2);
        output2.setObject(bytes);
        middleProcess.getPropertySet().put(OUTPUT2, output2);

        s.saveOrUpdate(middleProcess);
        t.commit();

        ZebraHelper.getInstance().getEngine().transitionTask(stop2);

        // Show run to stop3 on childs child
        AntelopeTaskInstance stop3 = checkTaskDef(STOP3,
                (AntelopeProcessInstance) middleProcess.getAllChildProcesses()
                        .get(0));
        AntelopeProcessInstance bottomProcess = (AntelopeProcessInstance) stop3
                .getProcessInstance();
        duration = System.currentTimeMillis() - start;
        log.debug("Computed stop 3 in:" + duration);

        t = s.beginTransaction();
        AntelopePropertySetEntry output3 = new AntelopePropertySetEntry();
        input3.setValue(OUTPUT3);
        bottomProcess.getPropertySet().put(OUTPUT3, output3);
        s.saveOrUpdate(bottomProcess);
        t.commit();

        ZebraHelper.getInstance().getEngine().transitionTask(stop3);

        duration = System.currentTimeMillis() - start;
        log.debug("Computed Transition in:" + duration);
        assertEquals(processInstance.getTaskInstances().size(), 0);
    }

    /**
     * @throws NestableException
     * @throws StartProcessException
     * @throws ComponentException
     * @throws TransitionException
     * @throws PersistenceException
     * @throws HibernateException
     */
    private void runWorkflowNoObjects() throws NestableException,
            StartProcessException, ComponentException, TransitionException,
            PersistenceException, HibernateException {
        log.debug("testing workflow Subprocess with Objects");

        AntelopeProcessInstance processInstance = ZebraHelper.getInstance()
                .createProcessPaused("TopLevel");
        assertNotNull(processInstance);

        log.debug("Starting Transition");
        long start = System.currentTimeMillis();
        processInstance.getPropertySet().put(INPUT2,
                new AntelopePropertySetEntry(INPUT2));
        ZebraHelper.getInstance().getEngine().startProcess(processInstance);

        // Should run to stop2 on the child
        AntelopeTaskInstance stop2 = checkTaskDef(STOP2,
                (AntelopeProcessInstance) processInstance
                        .getAllChildProcesses().get(0));
        AntelopeProcessInstance middleProcess = stop2
                .getAntelopeProcessInstance();
        long duration = System.currentTimeMillis() - start;
        log.debug("Computed stop 2 in:" + duration);

        Session s = PersistenceLocator.getInstance().getCurrentSession();
        Transaction t = s.beginTransaction();

        // now check passing up/down
        AntelopePropertySetEntry input2 = (AntelopePropertySetEntry) middleProcess
                .getPropertySet().get(INPUT2);
        assertTrue(input2.getValue().equals(INPUT2));
        AntelopePropertySetEntry input3 = new AntelopePropertySetEntry();
        input3.setValue(INPUT3);
        middleProcess.getPropertySet().put(INPUT3, input3);

        AntelopePropertySetEntry output2 = new AntelopePropertySetEntry();
        output2.setValue(OUTPUT2);
        middleProcess.getPropertySet().put(OUTPUT2, output2);

        s.saveOrUpdate(middleProcess);
        t.commit();

        ZebraHelper.getInstance().getEngine().transitionTask(stop2);

        // Show run to stop3 on childs child
        AntelopeTaskInstance stop3 = checkTaskDef(STOP3,
                (AntelopeProcessInstance) middleProcess.getAllChildProcesses()
                        .get(0));
        AntelopeProcessInstance bottomProcess = (AntelopeProcessInstance) stop3
                .getProcessInstance();
        log.debug("Computed stop 3 in:" + duration);

        t = s.beginTransaction();
        AntelopePropertySetEntry output3 = new AntelopePropertySetEntry();
        input3.setValue(OUTPUT3);
        bottomProcess.getPropertySet().put(OUTPUT3, output3);
        s.saveOrUpdate(bottomProcess);
        t.commit();

        ZebraHelper.getInstance().getEngine().transitionTask(stop3);
        duration = System.currentTimeMillis() - start;

        duration = System.currentTimeMillis() - start;
        log.debug("Computed Transition in:" + duration);
        assertEquals(processInstance.getTaskInstances().size(), 0);
    }

    /**
     * @param taskName
     * @throws TransitionException
     * @throws ComponentException
     * 
     * tests Task Definitions
     */
    private AntelopeTaskInstance checkTaskDef(String taskName,
            AntelopeProcessInstance antelopeProcessInstance)
            throws TransitionException, ComponentException {
        log.debug("testing task");

        assertEquals(antelopeProcessInstance.getTaskInstances().size(), 1);
        Iterator taskInstanceIterator = antelopeProcessInstance
                .getTaskInstances().iterator();
        AntelopeTaskInstance task = (AntelopeTaskInstance) taskInstanceIterator
                .next();
        assertNotNull(task);
        assertEquals(((AntelopeTaskDefinition) task.getTaskDefinition())
                .getName(), taskName);
        return task;
    }

}