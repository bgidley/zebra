package org.apache.fulcrum.crypto;

/*
 * Copyright 2001-2004 The Apache Software Foundation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License")
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import java.security.NoSuchAlgorithmException;
import java.util.Map;

/**
 * An implementation of CryptoService that uses either supplied crypto
 * Algorithms (provided in the component config xml file) or tries to get them via
 * the normal java mechanisms if this fails.
 *
 * This version has avalon dependencies removed.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:hps@intermeta.de">Henning P. Schmiedehausen</a>
 * @author <a href="mailto:ben@gidley.co.uk">Ben Gidley</a>
 * @version $Id: DefaultCryptoService.java,v 1.1 2005/11/24 16:56:02 bgidley Exp $
 *
 * @avalon.component name="crypto" lifestyle="singleton"
 * @avalon.service type="org.apache.fulcrum.crypto.CryptoService"
 */
public class DefaultCryptoService

implements CryptoService {

    /** Names of the registered algorithms and the wanted classes */
    private Map algorithm = null;    
    private String defaultAlgorithm = "java";

    /**
     * Returns a CryptoAlgorithm Object which represents the requested
     * crypto algorithm.
     *
     * @param algo      Name of the requested algorithm
     *
     * @return An Object representing the algorithm
     *
     * @throws NoSuchAlgorithmException  Requested algorithm is not available
     *
     */
    public CryptoAlgorithm getCryptoAlgorithm(String algo) throws NoSuchAlgorithmException {
        String cryptoClass = (String) algorithm.get(algo);
        CryptoAlgorithm ca = null;
        if (cryptoClass == null) {
            cryptoClass = (String) algorithm.get(defaultAlgorithm);
        }
        if (cryptoClass == null || cryptoClass.equalsIgnoreCase("none")) {
            throw new NoSuchAlgorithmException("TurbineCryptoService: No Algorithm for " + algo + " found");
        }
        try {
            //@todo should be created via factory service.  
            //Just trying to get something to work.
            //ca = (CryptoAlgorithm) factoryService.getInstance(cryptoClass);
            ca = (CryptoAlgorithm) Class.forName(cryptoClass).newInstance();
        } catch (Exception e) {
            throw new NoSuchAlgorithmException("TurbineCryptoService: Error instantiating " + cryptoClass + " for "
                    + algo);
        }
        ca.setCipher(algo);
        return ca;
    }

    public Map getAlgorithm() {
        return algorithm;
    }

    public void setAlgorithm(Map algorithm) {
        this.algorithm = algorithm;
    }

    public String getDefaultAlgorithm() {
        return defaultAlgorithm;
    }

    public void setDefaultAlgorithm(String defaultAlgorithm) {
        this.defaultAlgorithm = defaultAlgorithm;
    }
}
