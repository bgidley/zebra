/*
 * Created on 14-Feb-2005
 */
package com.anite.antelope.utils;

import net.sf.hibernate.cache.Cache;
import net.sf.hibernate.cache.CacheException;

/**
 * @author Ben.Gidley
 */
public class NullCache implements Cache {

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#get(java.lang.Object)
     */
    public Object get(Object arg0) throws CacheException {
        // TODO Auto-generated method stub
        return null;
    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#put(java.lang.Object, java.lang.Object)
     */
    public void put(Object arg0, Object arg1) throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#remove(java.lang.Object)
     */
    public void remove(Object arg0) throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#clear()
     */
    public void clear() throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#destroy()
     */
    public void destroy() throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#lock(java.lang.Object)
     */
    public void lock(Object arg0) throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#unlock(java.lang.Object)
     */
    public void unlock(Object arg0) throws CacheException {
        // TODO Auto-generated method stub

    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#nextTimestamp()
     */
    public long nextTimestamp() {
        // TODO Auto-generated method stub
        return 0;
    }

    /* (non-Javadoc)
     * @see net.sf.hibernate.cache.Cache#getTimeout()
     */
    public int getTimeout() {
        // TODO Auto-generated method stub
        return 0;
    }

}
