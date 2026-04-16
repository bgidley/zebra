package uk.co.gidley.zebra.inmemory.services;

import com.anite.zebra.core.api.IEngine;
import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;
import com.anite.zebra.core.exceptions.LockException;
import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.core.factory.exceptions.CreateObjectException;
import com.anite.zebra.core.factory.exceptions.StateFailureException;
import com.anite.zebra.core.state.api.*;
import org.apache.tapestry5.ioc.annotations.Marker;
import uk.co.gidley.zebra.service.om.definitions.ProcessDefinition;
import uk.co.gidley.zebra.service.om.definitions.TaskDefinition;
import uk.co.gidley.zebra.service.om.state.FOE;
import uk.co.gidley.zebra.service.om.state.ProcessInstance;
import uk.co.gidley.zebra.service.om.state.TaskInstance;

import java.util.ArrayList;
import java.util.List;

/**
 * Created by IntelliJ IDEA.
 * User: bgidley
 * Date: 28-Apr-2010
 * Time: 20:47:50
 */
public class InMemoryStateFactory implements IStateFactory {
    private InMemoryDatastore inMemoryDatastore;
    private InMemoryTransaction inMemoryTransaction;


    public InMemoryStateFactory(InMemoryDatastore inMemoryDatastore){
        this.inMemoryDatastore = inMemoryDatastore;
    }


    public ITransaction beginTransaction() throws StateFailureException {
        if (inMemoryTransaction != null){
            inMemoryTransaction.rollback();
        }

        inMemoryTransaction = new InMemoryTransaction();
        return inMemoryTransaction;
    }

    public void saveObject(IStateObject aso) throws StateFailureException {
        InMemoryAction inMemoryAction = new InMemoryAction(ActionType.save, aso);
        inMemoryTransaction.addAction(inMemoryAction);
    }

    public void deleteObject(IStateObject aso) throws StateFailureException {
        InMemoryAction inMemoryAction = new InMemoryAction(ActionType.delete, aso);
        inMemoryTransaction.addAction(inMemoryAction);
    }

    public IProcessInstance createProcessInstance(IProcessDefinition processDef) throws CreateObjectException {
        ProcessInstance processInstance = new ProcessInstance();
        processInstance.setProcessDefinitionId(((ProcessDefinition)processDef).getId());

        return processInstance;
    }

    public ITaskInstance createTaskInstance(ITaskDefinition taskDef, IProcessInstance processInstance, IFOE foe) throws CreateObjectException {
        TaskInstance taskInstance = new TaskInstance();
        taskInstance.setTaskDefinitionId(((TaskDefinition)taskDef).getId());
        taskInstance.setFOE(foe);
        taskInstance.setProcessInstance((ProcessInstance) processInstance);

        return taskInstance;
    }

    public IFOE createFOE(IProcessInstance processInstance) throws CreateObjectException {
        return new FOE((ProcessInstance) processInstance);
    }

    public void acquireLock(IProcessInstance processInstance, IEngine engine) throws LockException {

    }

    public void releaseLock(IProcessInstance processInstance, IEngine engine) throws LockException {

    }


    private class InMemoryTransaction implements ITransaction {

        public InMemoryTransaction(){
            this.inMemoryActionList = new ArrayList<InMemoryAction>();
        }

        private List<InMemoryAction> inMemoryActionList;

        public void commit() throws StateFailureException {
            for (InMemoryAction inMemoryAction : inMemoryActionList){
                // TODO do stuff
            }
        }

        public void rollback() throws StateFailureException {
            this.inMemoryActionList.clear();
        }

        public void addAction(InMemoryAction inMemoryAction) {
            inMemoryActionList.add(inMemoryAction);
        }
    }

    private class InMemoryAction {

        private ActionType type;
        private IStateObject aso;

        public InMemoryAction(ActionType save, IStateObject aso) {
            this.type = save;
            this.aso = aso;
        }

        public ActionType getType() {
            return type;
        }

        public IStateObject getAso() {
            return aso;
        }
    }

    public enum ActionType {
        save, delete
    }
}
