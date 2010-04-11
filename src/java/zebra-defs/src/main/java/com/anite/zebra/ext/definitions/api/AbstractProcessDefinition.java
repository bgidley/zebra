/*
 * Created on 02-Dec-2005 
 */
package com.anite.zebra.ext.definitions.api;

import java.util.Set;

import com.anite.zebra.core.definitions.api.IProcessDefinition;
import com.anite.zebra.core.definitions.api.ITaskDefinition;

public abstract class AbstractProcessDefinition implements IProcessVersion, IProcessDefinition, IPropertyGroupsAware {

    /**
     * TODO: put this method in a correct interface
     * 
     * sets the constructor class name - this class is called after the
     * process is initialised, but before the first task in the process is run.
     * 
     * should be null if there is no constructor for the process
     * 
     * @return
     */
    public abstract void setClassConstruct(String classConstruct);

    /**
     * 
     * TODO: put this method in a correct interface
     * 
     * sets the destructor class name - this class is called after the last
     * task in the process has completed, but before the process is marked as
     * "complete".
     * 
     * should be null if there is no destructor for the process
     * 
     * @return
     */
    public abstract void setClassDestruct(String classDestruct);

    /**
     * 
     * TODO: put this method in a correct interface
     * 
     * sets the first task in the process (the one to start the process it
     * with)
     * 
     * @return
     */
    public abstract void setFirstTask(ITaskDefinition taskDefinition);

    /**
     * TODO: put this method in a correct interface
     * @return
     */
    public abstract Set getRoutingDefinitions();

    /**
     * TODO: put this method in a correct interface
     * @return
     */
    public abstract Set getTaskDefinitions();

}
