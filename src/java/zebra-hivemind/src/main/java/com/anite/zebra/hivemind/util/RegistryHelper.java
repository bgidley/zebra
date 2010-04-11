package com.anite.zebra.hivemind.util;

import org.apache.fulcrum.hivemind.RegistryManager;
import org.hibernate.Session;

import com.anite.zebra.hivemind.impl.Zebra;

/**
 * Singleton to make it easier to find common items in the Registry when not
 * using injection.
 * 
 * @author ben.gidley
 * 
 */
public class RegistryHelper {
    
    private static RegistryHelper instance;
    private RegistryHelper(){
        // noop
    }
    
    public static RegistryHelper getInstance(){
        
        if (instance == null){
            instance = new RegistryHelper();
        }
        return instance;
    }
    
    
    public Session getSession() {
        return (Session) RegistryManager.getInstance().getRegistry().getService("fulcrum.hibernate.Session", Session.class);
    }
    
    public Zebra getZebra(){
    	return (Zebra) RegistryManager.getInstance().getRegistry().getService("zebra.zebra", Zebra.class);
    }
}
