package org.apache.fulcrum.security.authenticator;

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
import org.apache.fulcrum.security.entity.User;
import org.apache.fulcrum.security.util.DataBackendException;

/**
 * This class authenticates using the Fulcrum Crypto service a user and their
 * password
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @version $Id: CryptoAuthenticator.java,v 1.2 2006/01/17 09:17:24
 *          biggus_richus Exp $
 * @avalon.component name="crypto-authenticator"
 * @avalon.service type="org.apache.fulcrum.security.authenticator.Authenticator"
 */
public class CryptoAuthenticator implements Authenticator {
	boolean composed = false;

	private CryptoService cryptoService = null;

	private String algorithm = "java";

	private String cipher = "SHA-1";

	/**
	 * Authenticate an username with the specified password. If authentication
	 * is successful the method returns true. If it fails, it returns false If
	 * there are any problems, an exception is thrown.
	 * 
	 * 
	 * @param usernameAndDomain
	 *            an string in the format [domain]/[username].
	 * @param password
	 *            the user supplied password.
	 * @exception DataBackendException
	 *                if there is a problem accessing the storage.
	 */
	public boolean authenticate(User user, String password)
			throws DataBackendException {
		String output = getCryptoPassword(password);
		return output.equals(user.getPassword());
	}

	public String getAlgorithm() {
		return algorithm;
	}

	public void setAlgorithm(String algorithm) {
		this.algorithm = algorithm;
	}

	public String getCipher() {
		return cipher;
	}

	public void setCipher(String cipher) {
		this.cipher = cipher;
	}

	public void setCryptoService(CryptoService cryptoService) {
		this.cryptoService = cryptoService;
	}

	public String getCryptoPassword(String password)
			throws DataBackendException {
		try {
			CryptoAlgorithm ca = cryptoService.getCryptoAlgorithm(algorithm);
			ca.setCipher(cipher);
			return ca.encrypt(password);
		} catch (Exception e) {
			throw new DataBackendException(e.getMessage(), e);
		}
	}
}
