package org.apache.fulcrum.hivemind;

import org.apache.commons.logging.Log;

public class DummyService implements IDummy {
    private Log log;
    
    public Log getLog() {
        return this.log;
    }

    public void setLog(Log log) {
        this.log = log;
    }

    public void logAtDebug(String message){
        log.debug(message);
    }
}
