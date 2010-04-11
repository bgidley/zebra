package org.apache.fulcrum.security.hibernate.dynamic.model;

import java.util.Date;
import java.util.List;
import java.util.Set;

import javax.persistence.Basic;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.JoinColumn;
import javax.persistence.JoinTable;
import javax.persistence.ManyToMany;
import javax.persistence.Temporal;
import javax.persistence.TemporalType;

import org.apache.fulcrum.security.model.dynamic.entity.DynamicUser;
import org.hibernate.annotations.CollectionOfElements;
import org.hibernate.annotations.Type;

@Entity
public class HibernateDynamicUser extends DynamicUser {

    /**
	 * 
	 * @author richard.brooks
	 * Created on 14-Feb-2006
	 */
	private static final long serialVersionUID = 7837009296539278078L;

	@SuppressWarnings("unchecked")
	@Override
    @ManyToMany(mappedBy="delegators")
    public Set<HibernateDynamicUser> getDelegatees() {
        return super.getDelegatees();
    }

    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    @JoinTable(name = "HIBUSER_DELEGATES", joinColumns = { @JoinColumn(name = "DELEGATOR_ID") }, inverseJoinColumns = { @JoinColumn(name = "DELEGATEE_ID") })
    public Set<HibernateDynamicUser> getDelegators() {
        return super.getDelegators();
    }

    @Override
    @Basic
    public String getPassword() {
        return super.getPassword();
    }

    @Override
    @Id @GeneratedValue
    @Type(type = "long")
    public Object getId() {
        return super.getId();
    }

    @Override
    @Basic
    public String getName() {
        return super.getName();
    }

    @Override
    @Basic
    public boolean isDisabled() {
    	return super.isDisabled();
    }
    
    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    public Set<HibernateDynamicGroup> getGroupsAsSet() {
        return super.getGroupsAsSet();
    }
    
    @Override
    @Temporal(TemporalType.DATE)
    public Date getPasswordExpiryDate() {
    	return super.getPasswordExpiryDate();
    }
    
    @Override
    @Basic
    public long getLockTime() {
    	return super.getLockTime();
    }
    
    @Override
    @Basic
    public int getLoginAttempts() {
    	return super.getLoginAttempts();
    }
    
    @SuppressWarnings("unchecked")
	@Override
    @CollectionOfElements
    public List<String> getPasswordHistory() {
    	return super.getPasswordHistory();
    }
}