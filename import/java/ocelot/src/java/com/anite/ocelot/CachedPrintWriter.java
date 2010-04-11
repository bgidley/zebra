/*
 * Copyright 2004 Anite - Central Government Division
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

package com.anite.ocelot;

import java.io.OutputStream;
import java.io.Writer;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * @author Matthew.Norris
 */
public class CachedPrintWriter extends java.io.PrintWriter {

    /** logging */
    private static Log log = LogFactory.getLog(CachedPrintWriter.class);

    private String buf = "";

    /**
     * @param out
     * @param autoFlush
     */
    public CachedPrintWriter(OutputStream out, boolean autoFlush) {
        super(out, autoFlush);
        if (log.isInfoEnabled()) {
            log.info("CachedPrintWriter bln");
        }
    }

    /**
     * @param out
     */
    public CachedPrintWriter(OutputStream out) {
        super(out);
        if (log.isInfoEnabled()) {
            log.info("CachedPrintWriter");
        }
    }

    /**
     * @param out
     */
    public CachedPrintWriter(Writer out) {
        super(out);
        if (log.isInfoEnabled()) {
            log.info("CachedPrintWriter Writer");
        }
    }

    /**
     * @param out
     * @param autoFlush
     */
    public CachedPrintWriter(Writer out, boolean autoFlush) {
        super(out, autoFlush);
        if (log.isInfoEnabled()) {
            log.info("CachedPrintWriter Writer bln");
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#write(java.lang.String)
     */
    public void write(String s) {
        if (log.isInfoEnabled()) {
            log.info("write String");
        }
        buf = buf.concat(s);
        super.write(s);
    }

    /**
     * {@inheritDoc}
     */
    public String getBuffer() {
        return buf;
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#checkError()
     */
    /**
     * {@inheritDoc}
     */
    public boolean checkError() {
        return super.checkError();
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#close()
     */
    /**
     * {@inheritDoc}
     */
    public void close() {
        super.close();
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#flush()
     */
    /**
     * {@inheritDoc}
     */
    public void flush() {
        super.flush();
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(boolean)
     */
    /**
     * {@inheritDoc}
     */
    public void print(boolean b) {

        super.print(b);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(char)
     */
    /**
     * {@inheritDoc}
     */
    public void print(char c) {
        if (log.isInfoEnabled()) {
            log.info("print char");
        }
        super.print(c);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(char[])
     */
    /**
     * {@inheritDoc}
     */
    public void print(char[] s) {
        if (log.isInfoEnabled()) {
            log.info("print char[]");
        }
        super.print(s);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(double)
     */
    /**
     * {@inheritDoc}
     */
    public void print(double d) {
        super.print(d);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(float)
     */
    /**
     * {@inheritDoc}
     */
    public void print(float f) {

        super.print(f);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(int)
     */
    /**
     * {@inheritDoc}
     */
    public void print(int i) {

        super.print(i);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(long)
     */
    /**
     * {@inheritDoc}
     */
    public void print(long l) {

        super.print(l);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(java.lang.Object)
     */
    /**
     * {@inheritDoc}
     */
    public void print(Object obj) {
        if (log.isInfoEnabled()) {
            log.info("print object");
        }
        super.print(obj);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#print(java.lang.String)
     */
    /**
     * {@inheritDoc}
     */
    public void print(String s) {
        if (log.isInfoEnabled()) {
            log.info("print String");
        }
        buf = buf.concat(s);
        super.print(s);

    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println()
     */
    /**
     * {@inheritDoc}
     */
    public void println() {

        super.println();
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(boolean)
     */
    /**
     * {@inheritDoc}
     */
    public void println(boolean x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(char)
     */
    /**
     * {@inheritDoc}
     */
    public void println(char x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(char[])
     */
    /**
     * {@inheritDoc}
     */
    public void println(char[] x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(double)
     */
    /**
     * {@inheritDoc}
     */
    public void println(double x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(float)
     */
    /**
     * {@inheritDoc}
     */
    public void println(float x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(int)
     */
    /**
     * {@inheritDoc}
     */
    public void println(int x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(long)
     */
    /**
     * {@inheritDoc}
     */
    public void println(long x) {

        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(java.lang.Object)
     */
    /**
     * {@inheritDoc}
     */
    public void println(Object x) {
        if (log.isInfoEnabled()) {
            log.info("println Object");
        }
        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#println(java.lang.String)
     */
    /**
     * {@inheritDoc}
     */
    public void println(String x) {
        if (log.isInfoEnabled()) {
            log.info("println String");
        }
        super.println(x);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.PrintWriter#setError()
     */
    /**
     * {@inheritDoc}
     */
    protected void setError() {

        super.setError();
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#write(char[], int, int)
     */
    /**
     * {@inheritDoc}
     */
    public void write(char[] buf, int off, int len) {

        super.write(buf, off, len);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#write(char[])
     */
    /**
     * {@inheritDoc}
     */
    public void write(char[] buf) {

        super.write(buf);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#write(int)
     */
    /**
     * {@inheritDoc}
     */
    public void write(int c) {

        super.write(c);
    }

    /*
     * (non-Javadoc)
     * 
     * @see java.io.Writer#write(java.lang.String, int, int)
     */
    /**
     * {@inheritDoc}
     */
    public void write(String s, int off, int len) {
        if (log.isInfoEnabled()) {
            log.info("write String off len");
        }
        String n = "";
        if (off > 0) {
            n = n.concat(buf.substring(0, off) + s
                    + buf.substring(off + 1, buf.length()));
        } else {
            n = n.concat(s);
        }

        buf = n;
        super.write(s, off, len);
    }

}
