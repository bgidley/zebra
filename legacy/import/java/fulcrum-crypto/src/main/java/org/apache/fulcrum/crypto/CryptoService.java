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

/**
 * An implementation of CryptoService that uses either supplied crypto
 * Algorithms (provided in Fulcrum.properties) or tries to get them via
 * the normal java mechanisms if this fails.
 *
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:mcconnell@apache.org">Stephen McConnell</a>
 */
public interface CryptoService
{
   
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
  public CryptoAlgorithm getCryptoAlgorithm(String algo) throws NoSuchAlgorithmException;
}
