package org.apache.fulcrum.security.hibernate;

import org.apache.fulcrum.security.entity.SecurityEntity;
import org.apache.fulcrum.security.util.DataBackendException;
import org.hibernate.HibernateException;
import org.hibernate.Session;
import org.hibernate.Transaction;

/**
 * This implementation simply uses the Thread Session which is injected into here by Hivemind 
 * This service itself should be marked Threaded (if you want this to work!)
 * @author ben.gidley
 *
 */
public class PersistenceHelperHivemindImplementation implements PersistenceHelper {

    private Session session;

    public void removeEntity(SecurityEntity entity) throws DataBackendException {
        Transaction transaction = null;
        try {
            session = retrieveSession();
            transaction = session.beginTransaction();
            session.delete(entity);
            transaction.commit();
        } catch (HibernateException he) {
            try {
                transaction.rollback();
            } catch (HibernateException hex) {
            }
            throw new DataBackendException("Problem removing entity:" + he.getMessage(), he);
        }
    }
    
    public void disableEntity(SecurityEntity entity) throws DataBackendException {
    	entity.setDisabled(true);
    	updateEntity(entity);
    }

    public void updateEntity(SecurityEntity entity) throws DataBackendException {
        Transaction transaction = null;
        try {
            transaction = session.beginTransaction();
            session.saveOrUpdate(entity);
            transaction.commit();

        } catch (HibernateException he) {
            try {
                if (transaction != null) {
                    transaction.rollback();
                }
                if (he.getMessage().indexOf("Another object was associated with this id") > -1) {
                    session.close();
                    updateEntity(entity);
                } else {
                    throw new DataBackendException("updateEntity(" + entity + ")", he);
                }
            } catch (HibernateException hex) {
            }

        }
        return;

    }

    public void addEntity(SecurityEntity entity) throws DataBackendException {
        Transaction transaction = null;

        try {
            session = retrieveSession();
            transaction = session.beginTransaction();
            session.save(entity);
            transaction.commit();
        } catch (HibernateException he) {
            try {
                transaction.rollback();
            } catch (HibernateException hex) {
            }
            throw new DataBackendException("addEntity(s,name)", he);
        }
        return;
    }

    public Session retrieveSession() throws HibernateException {
        return session;
    }

    public Session getSession() {
        return session;
    }

    public void setSession(Session session) {
        this.session = session;
    }

}
