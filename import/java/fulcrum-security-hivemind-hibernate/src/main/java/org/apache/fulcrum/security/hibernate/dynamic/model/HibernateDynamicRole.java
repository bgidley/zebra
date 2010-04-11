package org.apache.fulcrum.security.hibernate.dynamic.model;

import java.util.Set;

import javax.persistence.Basic;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.ManyToMany;

import org.apache.fulcrum.security.model.dynamic.entity.DynamicRole;
import org.hibernate.annotations.Type;

@Entity
public class HibernateDynamicRole extends DynamicRole {

    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    public Set<HibernateDynamicGroup> getGroupsAsSet() {
        return super.getGroupsAsSet();
    }

    @SuppressWarnings("unchecked")
	@Override
    @ManyToMany
    public Set<HibernateDynamicPermission> getPermissionsAsSet() {
        return super.getPermissionsAsSet();
    }

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

    @Override
    @Basic
    public boolean isDisabled() {
    	return super.isDisabled();
    }
}