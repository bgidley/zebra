package org.apache.fulcrum.crypto;

import junit.framework.TestCase;

import org.apache.fulcrum.hivemind.RegistryManager;


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


/**
 * Basic testing of the Container
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:mcconnell@apache.org">Stephen McConnell</a>
 * @version $Id: CryptoServiceTest.java,v 1.1 2005/11/24 16:56:00 bgidley Exp $
 */
public class CryptoServiceTest extends TestCase
{
    private CryptoService sc = null;
    private static final String preDefinedInput = "Oeltanks";

      public void setUp() throws Exception
    {
        super.setUp();
        sc = (CryptoService) RegistryManager.getInstance().getRegistry().getService("fulcrum.crypto.Crypto", CryptoService.class);
    }

    public void testUnixCrypt() throws Exception
    {
        String preDefinedSeed = "z5";
        String preDefinedResult = "z5EQaXpuu059c";
       
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("unix");
        /*
       	* Test predefined Seed
       	*/
        ca.setSeed(preDefinedSeed);
        String output = ca.encrypt(preDefinedInput);
        assertEquals("Encryption failed ", preDefinedResult, output);
        /*
       	* Test random Seed
       	*
       	*/
        ca.setSeed(null);
        String result = ca.encrypt(preDefinedInput);
        ca.setSeed(result);
        output = ca.encrypt(preDefinedInput);
        assertEquals("Encryption failed ", output, result);
            
       
       
    }

    public void testClearCrypt() throws Exception
    {
        String preDefinedResult = "Oeltanks";
        
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("clear");
        String output = ca.encrypt(preDefinedInput);
        assertEquals("Encryption failed ", preDefinedResult, output);
       
    }

    public void testOldJavaCryptMd5() throws Exception
    {
        String preDefinedResult = "XSop0mncK19Ii2r2CUe2";
        
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("oldjava");
        ca.setCipher("MD5");
        String output = ca.encrypt(preDefinedInput);
        assertEquals("MD5 Encryption failed ", preDefinedResult, output);
            
    }
    public void testOldJavaCryptSha1() throws Exception
    {
        String preDefinedResult = "uVDiJHaavRYX8oWt5ctkaa7j";
       
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("oldjava");
        ca.setCipher("SHA1");
        String output = ca.encrypt(preDefinedInput);
        assertEquals("SHA1 Encryption failed ", preDefinedResult, output);
                  
    }
    public void testJavaCryptMd5() throws Exception
    {
        String preDefinedResult = "XSop0mncK19Ii2r2CUe29w==";
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("java");
        ca.setCipher("MD5");
        String output = ca.encrypt(preDefinedInput);
        assertEquals("MD5 Encryption failed ", preDefinedResult, output);
    }

    public void testJavaCryptSha1() throws Exception
    {
        String preDefinedResult = "uVDiJHaavRYX8oWt5ctkaa7j1cw=";
        CryptoAlgorithm ca = sc.getCryptoAlgorithm("java");
        ca.setCipher("SHA1");
        String output = ca.encrypt(preDefinedInput);
        assertEquals("SHA1 Encryption failed ", preDefinedResult, output);

    }
}
