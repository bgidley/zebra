package com.anite.antelope.security.hibernate;

import net.sf.hibernate.HibernateException;
import net.sf.hibernate.Session;
import net.sf.hibernate.Transaction;
import net.sf.hibernate.avalon.HibernateService;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.fulcrum.security.entity.SecurityEntity;
import org.apache.fulcrum.security.hibernate.PersistenceHelper;
import org.apache.fulcrum.security.spi.AbstractManager;
import org.apache.fulcrum.security.util.DataBackendException;
import org.apache.fulcrum.security.util.UnknownEntityException;

import com.anite.meercat.PersistenceException;
import com.anite.meercat.PersistenceLocator;

/**
 * 
 * This base implementation persists to a database via Hibernate. it provides
 * methods shared by all Hibernate SPI managers.
 * 
 * @author <a href="mailto:epugh@upstate.com">Mike Jones </a>
 */
public class MeercatPersistenceHelper extends AbstractManager implements
        PersistenceHelper {

    /** Logging */
    private static Log log = LogFactory.getLog(MeercatPersistenceHelper.class);

    protected HibernateService hibernateService;

    protected Transaction transaction;

    /**
     * Deletes an entity object
     * 
     * @param role
     *            The object to be removed
     * @throws DataBackendException
     *             if there was an error accessing the data backend.
     * @throws UnknownEntityException
     *             if the object does not exist.
     */
    public void removeEntity(SecurityEntity entity) throws DataBackendException {
        try {
            Session session = retrieveSession();
            transaction = session.beginTransaction();
            session.delete(entity);
            transaction.commit();
        } catch (HibernateException he) {
            try {
                transaction.rollback();
            } catch (HibernateException hex) {
            }
            throw new DataBackendException("Problem removing entity:"
                    + he.getMessage(), he);
        }
    }

    /**
     * Stores changes made to an object
     * 
     * @param role
     *            The object to be saved
     * @throws DataBackendException
     *             if there was an error accessing the data backend.
     * @throws UnknownEntityException
     *             if the role does not exist.
     */
    public void updateEntity(SecurityEntity entity) throws DataBackendException {
        try {

            Session session = retrieveSession();

            transaction = session.beginTransaction();
            session.update(entity);
            transaction.commit();

        } catch (HibernateException he) {
            try {
                if (transaction != null) {
                    transaction.rollback();
                }
                if (he.getMessage().indexOf(
                        "Another object was associated with this id") > -1) {
                    //session.close();
                    updateEntity(entity);
                } else {
                    throw new DataBackendException("updateEntity(" + entity
                            + ")", he);
                }
            } catch (HibernateException hex) {
                log.error(hex);
                throw new DataBackendException("updateEntity(" + entity
                        + ")", hex);
            }

        }
        return;
    }

    /**
     * adds an entity
     * 
     * @param role
     *            The object to be saved
     * @throws DataBackendException
     *             if there was an error accessing the data backend.
     * @throws UnknownEntityException
     *             if the role does not exist.
     */
    public void addEntity(SecurityEntity entity) throws DataBackendException {
        try {
            Session session = retrieveSession();
            transaction = session.beginTransaction();
            session.save(entity);
            transaction.commit();
        } catch (HibernateException he) {
            try {
                transaction.rollback();
            } catch (HibernateException hex) {
                log.error(hex);
            }
            throw new DataBackendException("addEntity(s,name)", he);
        }
        return;
    }

    /**
     * Returns a hibernate session 
     * 
     * @return An open hibernate session.
     * @throws HibernateException
     */
    public Session retrieveSession() throws HibernateException {

        try {
            return PersistenceLocator.getInstance().getCurrentSession();
        } catch (PersistenceException e) {
            log.error("Failed to get Hibernate session", e);
            throw new HibernateException(e);            
        }
    }

    /**
     * In some environments (like ECM) the service ends up getting it's own copy
     * of the HibernateService. In those environments, we might want to pass in
     * a different HibernateService instead.
     * 
     * @param hibernateService
     *            The hibernateService to set.
     */
    public void setHibernateService(HibernateService hibernateService) {
        this.hibernateService = hibernateService;
    }

    /**
     * Lazy loads the hibernateservice if it hasn't been requested yet.
     * 
     * @return the hibernate service
     */
    public HibernateService getHibernateService() throws HibernateException {
        return null;
    }

    public void dispose() {
        release(hibernateService);
        super.dispose();
    }

}