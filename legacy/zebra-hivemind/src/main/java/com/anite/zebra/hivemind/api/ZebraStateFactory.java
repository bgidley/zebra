package com.anite.zebra.hivemind.api;

import com.anite.zebra.core.factory.api.IStateFactory;
import com.anite.zebra.hivemind.om.state.ZebraTaskInstance;

public interface ZebraStateFactory extends IStateFactory {
    /**
     * Event listener for events (e.g. taskInstanceCreated)
     * @param listener
     */
    public abstract void addStateFactoryListener(StateFactoryListener listener);

    public abstract void removeStateFactoryListener(StateFactoryListener listener);
    
    public ZebraTaskInstance loadTaskInstance(Long zebraTaskInstanceId);

}