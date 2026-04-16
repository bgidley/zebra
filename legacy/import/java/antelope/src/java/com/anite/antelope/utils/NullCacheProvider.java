/**
 * Fake Cache used for testing speed issue
 */
package com.anite.antelope.utils;

import java.util.Properties;

import net.sf.hibernate.cache.Cache;
import net.sf.hibernate.cache.CacheException;
import net.sf.hibernate.cache.CacheProvider;

/**
 * @author Ben.Gidley
 */
public class NullCacheProvider implements CacheProvider {

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.CacheProvider#buildCache(java.lang.String, java.util.Properties)
     */
    public Cache buildCache(String arg0, Properties arg1) throws CacheException {

        return new NullCache();
    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.CacheProvider#nextTimestamp()
     */
    public long nextTimestamp() {

        return System.currentTimeMillis();
    }

}
