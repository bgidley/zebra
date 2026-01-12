/*
 * Created on 24-Nov-2003
 *
 */
package com.anite.antelope.modules.tools;

import org.apache.turbine.services.pull.ApplicationTool;
import org.apache.turbine.util.RunData;

/**
 * @author Peter.Courcoux
 *
 */
public class HttpHeadersTool implements ApplicationTool {

    RunData runData;
    /**
     * {@inheritDoc}
     */
	public final void setNoCacheHeaders() {
		runData.getResponse().setHeader("Cache-Control", "no-cache"); //HTTP 1.1
		runData.getResponse().setHeader("Pragma", "no-cache"); //HTTP 1.0
		runData.getResponse().setDateHeader("Expires", 0); //prevents caching at the proxy server
	}

    /* (non-Javadoc)
     * @see org.apache.turbine.services.pull.ApplicationTool#init(java.lang.Object)
     */
    public void init(Object arg0) {
        // TODO Auto-generated method stub
        runData = (RunData)arg0;
        
    }

    /* (non-Javadoc)
     * @see org.apache.turbine.services.pull.ApplicationTool#refresh()
     */
    public void refresh() {
        // TODO Auto-generated method stub
        
    }
}
