/*
 * Created on 24-Nov-2003
 *
 */
package com.anite.antelope.modules.tools;

import org.apache.turbine.services.pull.tools.TemplateLink;

/**
 * @author Peter.Courcoux
 *  
 */
public class TemplateLinkExt extends TemplateLink {

    /**
     * constant for "nocacheid"
     */
    private static final String NOCACHE = "nocacheid";


    /* (non-Javadoc)
     * @see org.apache.turbine.services.pull.tools.TemplateLink#getURI()
     */
    /**
     * {@inheritDoc}
     */
    public final String getURI() {
        super.addPathInfo(NOCACHE, new java.util.Date().getTime());
        String result = super.getURI();
        super.removePathInfo(NOCACHE);
        return result;
    }

    /* (non-Javadoc)
     * @see java.lang.Object#toString()
     */
    /**
     * {@inheritDoc}
     */
    public final String toString() {
        super.addPathInfo(NOCACHE, new java.util.Date().getTime());
        return super.toString();
    }

}
