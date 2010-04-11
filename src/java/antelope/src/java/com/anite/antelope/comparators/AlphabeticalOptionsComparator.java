/*
 * Created on 15-Dec-2004
 */
package com.anite.antelope.comparators;

import java.util.Comparator;

import com.anite.penguin.form.Option;

/**
 * Compares options so the captions sort alphabetically
 * @author Ben.Gidley
 */
public class AlphabeticalOptionsComparator implements Comparator {

    /* (non-Javadoc)
     * @see java.util.Comparator#compare(java.lang.Object, java.lang.Object)
     */
    public int compare(Object o1, Object o2) {
        Option option1 = (Option) o1;
        Option option2 = (Option) o2;
        return compare(option1,option2);
    }
    
    public int compare(Option option1, Option option2){
        return option1.getCaption().compareTo(option2.getCaption());  
    }

}
