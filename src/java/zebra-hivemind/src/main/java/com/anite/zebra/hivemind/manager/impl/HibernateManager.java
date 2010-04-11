/*
 * Copyright 2004, 2005 Anite 
 *    http://www.anite.com/publicsector
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.anite.zebra.hivemind.manager.impl;

import java.lang.reflect.ParameterizedType;
import java.util.List;

import org.hibernate.Session;
import org.hibernate.Transaction;

import com.anite.zebra.hivemind.manager.BaseManager;

public abstract class HibernateManager<T> implements BaseManager<T> {

    private Session session;

   

    protected Session getSession() {
        return session;
    }

    public void setSession(Session session) {
        this.session = session;
    }

    public void delete(T object) {

        Transaction tx = session.beginTransaction();
        session.delete(object);
        tx.commit();

    }

    @SuppressWarnings("unchecked")
    public T get(Long id) {
        return (T) session.load(getParameterClazz(), id);
    }

    public List<T> getAll() {
       return (List<T>) session.createQuery("from " + getParameterClazz());
    }

    public void saveOrUpdate(T object) {
        Transaction tx = session.beginTransaction();
        session.saveOrUpdate(object);
        tx.commit();
    }

    private Class getParameterClazz() {
        ParameterizedType ptype = (ParameterizedType) this.getClass().getGenericSuperclass();
        return (Class) ptype.getActualTypeArguments()[0];
    }

}