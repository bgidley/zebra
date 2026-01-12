package org.apache.fulcrum.security.util;

/**
 * Thrown when a locked user attempts to authenticate.
 * 
 * @author richard.brooks
 * Created on Jan 13, 2006
 */

public class EntityDisabledException extends TurbineSecurityException {

	private static final long serialVersionUID = 3325662922250048072L;

	/**
     * Construct a UserDisabledException with specified detail message.
     * @param msg The detail message.
     *
     * @author richard.brooks
     * Created on Mar 17, 2006
     */
	public EntityDisabledException(String msg)
    {
        super(msg);
    }
}
