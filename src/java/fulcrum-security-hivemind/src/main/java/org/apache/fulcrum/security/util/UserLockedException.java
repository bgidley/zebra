package org.apache.fulcrum.security.util;

/**
 * Thrown when a locked user attempts to authenticate.
 * 
 * @author richard.brooks
 * Created on Jan 13, 2006
 */

public class UserLockedException extends TurbineSecurityException {

	private static final long serialVersionUID = 8284553869426136480L;

	/**
     * Construct a UserLockedException with specified detail message.
     * @param msg The detail message.
     *
     * @author richard.brooks
     * Created on Jan 13, 2006
     */
	public UserLockedException(String msg)
    {
        super(msg);
    }
}
