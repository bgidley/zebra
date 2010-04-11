package com.anite.antelope.utils;

import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.SoftReference;
import java.lang.ref.WeakReference;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.WeakHashMap;

/**
 * Cache with weak keys and soft values.
 * 
 * @author Bob Lee (crazybob@crazybob.org)
 */
public abstract class Cache {

	static Object NULL_VALUE = new Object();
	
	Map map;
	ReferenceQueue queue = new ReferenceQueue();
	
	/**
	 * Creates cache.
	 * 
	 * @param weakKeys Use weak references for keys.
	 */
	public Cache(boolean weakKeys) {
		this.map = (weakKeys) ? 
			(Map) new WeakHashMap() : new HashMap();
		this.map = Collections.synchronizedMap(this.map);
	}
	
	/**
	 * Defaults to weak keys.
	 */
	public Cache() {
		this(true);
	}
	
	/**
	 * Creates value for key. Called by getter if 
	 * value isn't cached.
	 */
	protected abstract Object create(Object key);
	
	/**
	 * Gets value for key. Creates if necessary.
	 */
	public Object get(Object key) {
		Object value = internalGet(key);
		if (value == null) {
			value = create(key);
			if (value == null)
				value = NULL_VALUE;
			this.map.put(key, 
				new ValueReference(key, value));
		}
		return (value == NULL_VALUE) ? null : value;
	}
	
	void cleanUp() {
		Reference reference;
		while ((reference = this.queue.poll()) != null)
			map.remove(
				((ValueReference) reference).getKey());
	}
	
	Object internalGet(Object key) {
		cleanUp();
		Reference reference = (Reference) map.get(key);
		return (reference == null) ? 
			null : reference.get();
	}
	
	class ValueReference extends SoftReference {
		
		WeakReference keyReference;
		
		ValueReference(Object key, Object value) {
			super(value, queue);
			this.keyReference = new WeakReference(key); 
		}
		
		Object getKey() {
			return this.keyReference.get();
		}
	}
}
