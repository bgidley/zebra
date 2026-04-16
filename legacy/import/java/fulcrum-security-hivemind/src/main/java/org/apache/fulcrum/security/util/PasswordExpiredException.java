package org.apache.fulcrum.security.util;

/**
 * Thrown when a user's password has expired.
 * 
 * @author richard.brooks
 * Created on Jan 13, 2006
 */

public class PasswordExpiredException extends TurbineSecurityException {
	private static final long serialVersionUID = 7248522630844763772L;

	/**
     * Construct a PasswordExpiredException with specified detail message.
     * @param msg The detail message.
     *
     * @author richard.brooks
     * Created on Jan 13, 2006
     */
	public PasswordExpiredException(String msg)
    {
        super(msg);
    }

}
