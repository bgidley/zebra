package org.apache.fulcrum.security.hibernate.dynamic.model;

import java.util.Set;

import javax.persistence.Basic;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.ManyToMany;

import org.apache.fulcrum.security.model.dynamic.entity.DynamicGroup;
import org.hibernate.annotations.Type;

@Entity
public class HibernateDynamicGroup extends DynamicGroup {

    @Override
    @Id @GeneratedValue
    @Type(type="long")
    public Object getId() {
        return super.getId();
    }

    @Override
    @Basic
    public String getName() {
        return super.getName();
    }

    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    public Set<HibernateDynamicRole> getRolesAsSet() {

        return super.getRolesAsSet();
    }

    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    public Set<HibernateDynamicUser> getUsersAsSet() {
        return super.getUsersAsSet();
    }

    @Override
    @Basic
    public boolean isDisabled() {
    	return super.isDisabled();
    }
}