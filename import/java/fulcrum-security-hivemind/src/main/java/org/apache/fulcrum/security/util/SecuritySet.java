package org.apache.fulcrum.security.util;

/*
 *  Copyright 2001-2004 The Apache Software Foundation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

import java.io.Serializable;
import java.util.Collection;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.apache.commons.lang.StringUtils;
import org.apache.fulcrum.security.entity.SecurityEntity;

/**
 * This class represents a set of Security Entities. It makes it easy to build a
 * UI. It wraps a TreeSet object to enforce that only relevant methods are
 * available. TreeSet's contain only unique Objects (no duplicates) based on the
 * ID. They may or may not have a name, that depends on the implementation. Want
 * to get away frm requiring an ID and a name... Nothing should force Name to be
 * unique in the basic architecture of Fulcrum Security.
 * 
 * I have reimplemented this as a quick fix to the hibernate issues this causes.
 * This now wraps the set looking up everything at run time.
 * 
 * @author <a href="mailto:epugh@upstate.com">Eric Pugh</a>
 * @author <a href="mailto:jmcnally@collab.net">John D. McNally</a>
 * @author <a href="mailto:bmclaugh@algx.net">Brett McLaughlin</a>
 * @author <a href="mailto:marco@intermeta.de">Marco Kn&uuml;ttel</a>
 * @author <a href="mailto:hps@intermeta.de">Henning P. Schmiedehausen</a>
 * @version $Id: SecuritySet.java,v 1.3 2006/07/19 09:15:16 bgidley Exp $
 */
public abstract class SecuritySet implements Serializable, Set {
	protected Set wrappedSet;

	/*
	 * To enable the typesafe handling, make this abstract and rely on the
	 * implementing classes like RoleSet to properly cast the Object type.
	 * 
	 * @see java.util.Collection#add(java.lang.Object)
	 */
	public abstract boolean add(Object o);

	
	public SecuritySet(){
		this.wrappedSet = new HashSet();
	}
	
	/**
	 * Returns a set of security objects in this object.
	 * 
	 * @return A Set Object
	 * 
	 */
	@SuppressWarnings("unchecked")
	public Set getSet() {
		return wrappedSet;
	}

	/**
	 * Returns a set of Names in this Object.
	 * 
	 * @return The Set of Names in this Object, backed by the actual data.
	 */
	@SuppressWarnings("unchecked")
	public Set getNames() {
		Set names = new HashSet();
		for (Iterator i = getSet().iterator(); i.hasNext();) {
			SecurityEntity se = (SecurityEntity) i.next();
			names.add(se.getName());
		}
		return names;
	}

	/**
	 * Returns a set of Id values in this Object.
	 * 
	 * @return The Set of Ids in this Object, backed by the actual data.
	 */
	@SuppressWarnings("unchecked")
	public Set getIds() {
		Set ids = new HashSet();
		for (Iterator i = getSet().iterator(); i.hasNext();) {
			SecurityEntity se = (SecurityEntity) i.next();
			ids.add(se.getId());
		}
		return ids;
	}

	/**
	 * Removes all Objects from this Set.
	 */
	public void clear() {
		wrappedSet.clear();
	}

	/**
	 * Searches if an Object with a given name is in the Set
	 * 
	 * @param roleName
	 *            Name of the Security Object.
	 * @return True if argument matched an Object in this Set; false if no
	 *         match.
	 */
	public boolean containsName(String name) {

		return (StringUtils.isNotEmpty(name)) ? getNames().contains(
				name.toLowerCase()) : false;

	}

	/**
	 * Searches if an Object with a given Id is in the Set
	 * 
	 * @param id
	 *            Id of the Security Object.
	 * @return True if argument matched an Object in this Set; false if no
	 *         match.
	 */
	public boolean containsId(Object id) {
		return (id == null) ? false : getIds().contains(id);
	}

	/**
	 * Returns an Iterator for Objects in this Set.
	 * 
	 * @return An iterator for the Set
	 */
	public Iterator iterator() {
		return wrappedSet.iterator();
	}

	/**
	 * Returns size (cardinality) of this set.
	 * 
	 * @return The cardinality of this Set.
	 */
	public int size() {
		return wrappedSet.size();
	}

	/**
	 * list of role names in this set
	 * 
	 * @return The string representation of this Set.
	 */
	public String toString() {

		return wrappedSet.toString();
	}

	// methods from Set
	public boolean addAll(Collection collection) {
		return add((Collection) collection);
	}

	public boolean isEmpty() {
		return wrappedSet.isEmpty();
	}

	public boolean containsAll(Collection collection) {

		return wrappedSet.containsAll(collection);
	}

	public boolean removeAll(Collection collection) {
		return wrappedSet.removeAll(collection);
	}

	public boolean retainAll(Collection collection) {
		return wrappedSet.retainAll(collection);
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see java.util.Collection#toArray()
	 */
	public Object[] toArray() {
		return wrappedSet.toArray();
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see java.util.Collection#contains(java.lang.Object)
	 */
	public boolean contains(Object o) {
		if (o == null) {
			return false;
		} else {
			return containsName(((SecurityEntity) o).getName());
		}
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see java.util.Collection#remove(java.lang.Object)
	 */
	public boolean remove(Object o) {
		return wrappedSet.remove(o);
	}

	/*
	 * (non-Javadoc)
	 * 
	 * @see java.util.Collection#toArray(java.lang.Object[])
	 */
	@SuppressWarnings("unchecked")
	public Object[] toArray(Object[] a) {
		return wrappedSet.toArray(a);
	}

	public SecurityEntity getByName(String name) {
		SecurityEntity securityEntity = null;
		for (Iterator i = getSet().iterator(); i.hasNext();) {
			SecurityEntity se = (SecurityEntity) i.next();
			if (se.getName().equalsIgnoreCase(name)) {
				securityEntity = se;
				break;
			}
		}
		return securityEntity;

	}

	public SecurityEntity getById(Object id) {
		SecurityEntity securityEntity = null;
		for (Iterator i = getSet().iterator(); i.hasNext();) {
			SecurityEntity se = (SecurityEntity) i.next();
			if (se.getId().equals(id)) {
				securityEntity = se;
				break;
			}
		}
		return securityEntity;
	}
}
