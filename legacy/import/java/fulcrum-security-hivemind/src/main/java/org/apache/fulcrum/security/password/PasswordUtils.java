package org.apache.fulcrum.security.password;
/*
 *  Copyright 2001-2004 The Apache Software Foundation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */
import org.apache.fulcrum.crypto.CryptoAlgorithm;
import org.apache.fulcrum.crypto.CryptoService;

/**
 * This class should provide any password functions needed.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: PasswordUtils.java,v 1.1 2005/11/14 18:20:52 bgidley Exp $
 */
public class PasswordUtils
{
    private PasswordUtils(){

    }


	/**
	   * This method provides client-side encryption of passwords.
	   *
	   * If <code>secure.passwords</code> are enabled in TurbineResources,
	   * the password will be encrypted, if not, it will be returned unchanged.
	   * The <code>secure.passwords.algorithm</code> property can be used
	   * to chose which digest algorithm should be used for performing the
	   * encryption. <code>SHA</code> is used by default.
	   *
	   * @param password the password to process
	   * @return processed password
	   */
	  public String encryptPassword(String password) throws Exception
	  {
		  return encryptPassword(password, null);
	  }

	  /**
	   * This method provides client-side encryption of passwords.
	   *
	   * If <code>secure.passwords</code> are enabled in TurbineResources,
	   * the password will be encrypted, if not, it will be returned unchanged.
	   * The <code>secure.passwords.algorithm</code> property can be used
	   * to chose which digest algorithm should be used for performing the
	   * encryption. <code>SHA</code> is used by default.
	   *
	   * The used algorithms must be prepared to accept null as a
	   * valid parameter for salt. All algorithms in the Fulcrum Cryptoservice
	   * accept this.
	   *
	   * @param password the password to process
	   * @param salt     algorithms that needs a salt can provide one here
	   * @return processed password
	   */

	  public String encryptPassword(String password, String salt) throws Exception
	  {
		  if (password == null)
		  {
			  return null;
		  }

		  // @todo Need to pass this in..

		  String secure = null;/*getConfiguration().getString(
				  SecurityService.SECURE_PASSWORDS_KEY,
				  SecurityService.SECURE_PASSWORDS_DEFAULT).toLowerCase();
*/
//@todo also need to pass this in..
		  String algorithm = null;/*getConfiguration().getString(
				  SecurityService.SECURE_PASSWORDS_ALGORITHM_KEY,
				  SecurityService.SECURE_PASSWORDS_ALGORITHM_DEFAULT);*/

		  CryptoService cs = null;//  @todo Must fix this line.   TurbineCrypto.getService();

		  if (cs != null && (secure.equals("true") || secure.equals("yes")))
		  {

				  CryptoAlgorithm ca = cs.getCryptoAlgorithm(algorithm);

				  ca.setSeed(salt);

				  String result = ca.encrypt(password);

				  return result;

		  }
		  else
		  {
			  return password;
		  }
	  }
    /**
    	 * Checks if a supplied password matches the encrypted password
    	 *
    	 * @param checkpw      The clear text password supplied by the user
    	 * @param encpw        The current, encrypted password
    	 *
    	 * @return true if the password matches, else false
    	 *
    	 */
    public boolean checkPassword(String checkpw, String encpw) throws Exception
    {
        String result = encryptPassword(checkpw, encpw);
        return (result == null) ? false : result.equals(encpw);
    }
}
