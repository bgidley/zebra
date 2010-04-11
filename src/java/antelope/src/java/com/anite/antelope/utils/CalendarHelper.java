/*
 * Created on 10-Sep-2004 by John.Rae
 * 
 *
 */
package com.anite.antelope.utils;

import java.sql.Date;
import java.sql.Time;
import java.text.DateFormatSymbols;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Iterator;
import java.util.List;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

/**
 * @author John.Rae A Calendar Helper to simplify use of dates and times. Makes
 *         sure that timezone is always correct
 */
public class CalendarHelper {

    private static final int DAY = 86400000;

    private static CalendarHelper instance = null;

    private static final String DEFAULT_DATE_FORMAT = "dd/MM/yyyy";

    private static final String DEFAULT_TIME_FORMAT = "HH:mm";

    private static final String DEFAULT_DATE_TIME_FORMAT = DEFAULT_DATE_FORMAT
            + " " + DEFAULT_TIME_FORMAT;

    /** Class logger */
    private static Log log = LogFactory.getLog(CalendarHelper.class);

    private CalendarHelper() {
    }

    /**
     * Gets a calender (always use this incase we need to set a timezone)
     */
    public Calendar getCalendar() {
        return Calendar.getInstance();
    }

    public static CalendarHelper getInstance() {
        if (instance == null) {
            instance = new CalendarHelper();
        }
        return instance;
    }

    /**
     * Gets the SQL Date for now
     * 
     * @return
     */
    public java.sql.Date getSqlDate() {
        Calendar cal = this.getCalendar();
        return this.getSqlDate(cal);
    }

    /**
     * Convert passed calender to a SQLDate
     * 
     * @param cal
     * @return
     */
    public java.sql.Date getSqlDate(Calendar cal) {
        cal.set(Calendar.MILLISECOND, 0);
        cal.set(Calendar.HOUR, 0);
        cal.set(Calendar.MINUTE, 0);
        cal.set(Calendar.SECOND, 0);
        return new Date(cal.getTime().getTime());
    }

    /**
     * Gets a SQL Time object for the passed calender
     * 
     * @param cal
     * @return
     */
    public Time getSqlTime(Calendar cal) {
        cal.set(Calendar.YEAR, 1970);
        cal.set(Calendar.MONTH, 1);
        cal.set(Calendar.DATE, 1);

        return new Time(cal.getTimeInMillis());
    }

    /**
     * Gets the time now
     * 
     * @return
     */
    public Time getSqlTime() {
        return getSqlTime(this.getCalendar());
    }

    /**
     * Get the calender for midnight today
     * 
     * @return
     */
    public Calendar getTodayMidnightDate() {
        Calendar cal = this.getCalendar();
        cal.set(cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal
                .get(Calendar.DATE), 0, 0, 0);
        //set the milliseconds to zero
        cal.set(Calendar.MILLISECOND, 0);
        return cal;
    }

    public Date getTodayMidnightSqlDate() {
        Calendar cal = this.getTodayMidnightDate();
        return new Date(cal.getTime().getTime());
    }

    public Date getFutureSqlDate(Date startDate, int field, int amount) {
        Calendar cal = this.getCalendar(startDate);
        cal.add(field, amount);
        return new Date(cal.getTime().getTime());
    }

    public Calendar getMidnightDate(Calendar date) {
        Calendar cal = date;
        cal.set(cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal
                .get(Calendar.DATE), 0, 0, 0);
        //set the milliseconds to zero
        cal.set(Calendar.MILLISECOND, 0);
        return cal;
    }

    public Date getMidnightDate(Date date) {
        Calendar cal = getCalendar(date);
        cal.set(cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal
                .get(Calendar.DATE), 0, 0, 0);
        //set the milliseconds to zero
        cal.set(Calendar.MILLISECOND, 0);
        return getSqlDate(cal);
    }

    public java.util.Date getDateTimeNow() {
        Calendar cal = this.getCalendar();
        return new java.util.Date(cal.getTime().getTime());
    }

    /**
     * @param periodStartDate2
     * @param periodEndDate2
     * @return
     */
    public int getAmountOfDays(Date start, Date end) {

        Date startDate = CalendarHelper.getInstance().getMidnightDate(start);
        Date endDate = CalendarHelper.getInstance().getMidnightDate(end);

        long diff = endDate.getTime() - startDate.getTime();

        return (new Long(diff / DAY)).intValue() + 1;
    }

    public Calendar getCalendar(Date sqlDate) {
        Calendar cal = this.getCalendar();
        cal.setTime(sqlDate);
        return cal;
    }

    public Calendar getCalendar(long timeInMillies) {
        Calendar cal = this.getCalendar();
        cal.setTimeInMillis(timeInMillies);
        return cal;
    }

    public Date addTime(Date date, int period, int amount) {
        Calendar cal = getCalendar(date);
        cal.add(period, amount);
        return getSqlDate(cal);
    }

    public String addDay(Date date) {
        Calendar cal = getCalendar(date);

        String dayNames[] = new DateFormatSymbols().getWeekdays();

        int dayno = cal.get(Calendar.DAY_OF_WEEK);
        String day = dayNames[dayno];

        return day;
    }

    public List getListOfDates(Date startDate, Date endDate) {
        List dateList = new ArrayList();
        Date dateToAdd = startDate;

        while (true) {
            dateList.add(dateToAdd);

            if (dateToAdd.compareTo(endDate) != 0) {
                // add a day
                dateToAdd = addTime(dateToAdd, Calendar.DAY_OF_YEAR, 1);
            } else {
                //stop the loop
                break;
            }
        }
        return dateList;
    }

    public List getListOfDays(List listofdays) {
        List dateList = new ArrayList();
        Iterator itr = listofdays.iterator();
        while (itr.hasNext()) {
            Date checkdate = (Date) itr.next();

            // add a day
            String day = addDay(checkdate);
            dateList.add(day);

        }
        return dateList;
    }

    /**
     * Gets a date formatted DD/MM/YYYY
     * 
     * @param dateCreated
     */
    public String getFormattedDate(java.util.Date dateCreated) {
        if (dateCreated == null) {
            return "";
        }
        SimpleDateFormat sdf = new SimpleDateFormat(DEFAULT_DATE_FORMAT);
        return sdf.format(dateCreated);
    }

    /**
     * @param dateCreated
     */
    public String getFormattedTime(java.util.Date time) {
        if (time == null) {
            return "";
        }
        SimpleDateFormat sdf = new SimpleDateFormat(DEFAULT_TIME_FORMAT);
        return sdf.format(time);
    }

    /**
     * Returns a Date object from 1 String components: Date in DEFAULT DATE
     * FORMAT
     * 
     * @param date
     *            date
     * @return date object
     */
    public Date parseDate(String date) {
        if (date == null) {
            return null;
        }

        SimpleDateFormat dateFormat = new SimpleDateFormat(DEFAULT_DATE_FORMAT);
        try {
            return new Date(dateFormat.parse(date).getTime());
        } catch (ParseException e) {
            log.debug("date parse error");
            return null;
        }

    }

    /**
     * Converted passed string into a sql time object returns null if not a time
     */
    public Time parseTime(String time) {
        if (time == null) {
            return null;
        }
        SimpleDateFormat dateFormat = new SimpleDateFormat(DEFAULT_TIME_FORMAT);
        try {
            return new Time(dateFormat.parse(time).getTime());
        } catch (ParseException e) {
            return null;
        }
    }

    public java.util.Date parseDateTime(String dateTime) {
        if (dateTime == null) {
            return null;
        }
        SimpleDateFormat dateFormat = new SimpleDateFormat(
                DEFAULT_DATE_TIME_FORMAT);
        try {
            return new Date(dateFormat.parse(dateTime).getTime());
        } catch (ParseException e) {
            return null;
        }
    }

    /**
     * @param startDate
     * @return
     */
    public String getFormattedDateTime(java.util.Date date) {
        if (date == null) {
            return "";
        }
        SimpleDateFormat sdf = new SimpleDateFormat(DEFAULT_DATE_TIME_FORMAT);
        return sdf.format(date);
    }
}