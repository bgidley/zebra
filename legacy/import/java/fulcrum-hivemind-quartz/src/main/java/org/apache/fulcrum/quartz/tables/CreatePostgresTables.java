/*
 * Copyright 2005 Anite - Central Government Division
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
package org.apache.fulcrum.quartz.tables;

/**
 * use this for postgreSQL
 * @author peter
 *
 */
public class CreatePostgresTables extends CreateTables{
	
	
	public void addCommands() {
	addSql("DROP TABLE quartz.qrtz_locks;");
	addSql("drop table quartz.qrtz_job_listeners;");
	addSql("drop table quartz.qrtz_trigger_listeners;");
	addSql("drop table quartz.qrtz_fired_triggers;");
	addSql("DROP TABLE quartz.qrtz_paused_trigger_grps;");
	addSql("DROP TABLE quartz.qrtz_scheduler_state;");
	addSql("drop table quartz.qrtz_simple_triggers;");
	addSql("drop table quartz.qrtz_cron_triggers;");
	addSql("DROP TABLE quartz.qrtz_blob_triggers;");
	addSql("drop table quartz.qrtz_triggers;");
	addSql("drop table quartz.qrtz_job_details;");
	addSql("drop table quartz.qrtz_calendars;");
	addSql("drop schema quartz;");
	addSql("create schema quartz;");
	addSql("set search_path to public, quartz;");
	addSql("CREATE TABLE quartz.qrtz_locks (LOCK_NAME  VARCHAR(40) NOT NULL, PRIMARY KEY (LOCK_NAME));");
	addSql("CREATE TABLE quartz.qrtz_job_details (JOB_NAME  VARCHAR(80) NOT NULL, JOB_GROUP VARCHAR(80) NOT NULL, DESCRIPTION VARCHAR(120) NULL, JOB_CLASS_NAME VARCHAR(128) NOT NULL, IS_DURABLE BOOL NOT NULL, IS_VOLATILE BOOL NOT NULL, IS_STATEFUL BOOL NOT NULL, REQUESTS_RECOVERY BOOL NOT NULL, JOB_DATA BYTEA NULL, PRIMARY KEY (JOB_NAME,JOB_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_job_listeners ( JOB_NAME  VARCHAR(80) NOT NULL, JOB_GROUP VARCHAR(80) NOT NULL, JOB_LISTENER VARCHAR(80) NOT NULL, PRIMARY KEY (JOB_NAME,JOB_GROUP,JOB_LISTENER), FOREIGN KEY (JOB_NAME,JOB_GROUP) REFERENCES QRTZ_JOB_DETAILS(JOB_NAME,JOB_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_triggers (TRIGGER_NAME VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, JOB_NAME  VARCHAR(80) NOT NULL, JOB_GROUP VARCHAR(80) NOT NULL, IS_VOLATILE BOOL NOT NULL, DESCRIPTION VARCHAR(120) NULL, NEXT_FIRE_TIME BIGINT NULL, PREV_FIRE_TIME BIGINT NULL, TRIGGER_STATE VARCHAR(16) NOT NULL, TRIGGER_TYPE VARCHAR(8) NOT NULL, START_TIME BIGINT NOT NULL, END_TIME BIGINT NULL, CALENDAR_NAME VARCHAR(80) NULL, MISFIRE_INSTR SMALLINT NULL, JOB_DATA BYTEA NULL, PRIMARY KEY (TRIGGER_NAME,TRIGGER_GROUP), FOREIGN KEY (JOB_NAME,JOB_GROUP)REFERENCES QRTZ_JOB_DETAILS(JOB_NAME,JOB_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_simple_triggers ( TRIGGER_NAME VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, REPEAT_COUNT BIGINT NOT NULL, REPEAT_INTERVAL BIGINT NOT NULL, TIMES_TRIGGERED BIGINT NOT NULL, PRIMARY KEY (TRIGGER_NAME,TRIGGER_GROUP), FOREIGN KEY (TRIGGER_NAME,TRIGGER_GROUP) REFERENCES QRTZ_TRIGGERS(TRIGGER_NAME,TRIGGER_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_cron_triggers (TRIGGER_NAME VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, CRON_EXPRESSION VARCHAR(80) NOT NULL, TIME_ZONE_ID VARCHAR(80), PRIMARY KEY (TRIGGER_NAME,TRIGGER_GROUP), FOREIGN KEY (TRIGGER_NAME,TRIGGER_GROUP) REFERENCES QRTZ_TRIGGERS(TRIGGER_NAME,TRIGGER_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_blob_triggers ( TRIGGER_NAME VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, BLOB_DATA BYTEA NULL, PRIMARY KEY (TRIGGER_NAME,TRIGGER_GROUP), FOREIGN KEY (TRIGGER_NAME,TRIGGER_GROUP) REFERENCES QRTZ_TRIGGERS(TRIGGER_NAME,TRIGGER_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_trigger_listeners ( TRIGGER_NAME  VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, TRIGGER_LISTENER VARCHAR(80) NOT NULL, PRIMARY KEY (TRIGGER_NAME,TRIGGER_GROUP,TRIGGER_LISTENER), FOREIGN KEY (TRIGGER_NAME,TRIGGER_GROUP) REFERENCES QRTZ_TRIGGERS(TRIGGER_NAME,TRIGGER_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_calendars ( CALENDAR_NAME  VARCHAR(80) NOT NULL, CALENDAR BYTEA NOT NULL, PRIMARY KEY (CALENDAR_NAME));");
	addSql("CREATE TABLE quartz.qrtz_paused_trigger_grps (TRIGGER_GROUP  VARCHAR(80) NOT NULL, PRIMARY KEY (TRIGGER_GROUP));");
	addSql("CREATE TABLE quartz.qrtz_fired_triggers  ( ENTRY_ID VARCHAR(95) NOT NULL, TRIGGER_NAME VARCHAR(80) NOT NULL, TRIGGER_GROUP VARCHAR(80) NOT NULL, IS_VOLATILE BOOL NOT NULL, INSTANCE_NAME VARCHAR(80) NOT NULL, FIRED_TIME BIGINT NOT NULL, STATE VARCHAR(16) NOT NULL, JOB_NAME VARCHAR(80) NULL, JOB_GROUP VARCHAR(80) NULL, IS_STATEFUL BOOL NULL, REQUESTS_RECOVERY BOOL NULL, PRIMARY KEY (ENTRY_ID));");
	addSql("CREATE TABLE quartz.qrtz_scheduler_state ( INSTANCE_NAME VARCHAR(80) NOT NULL, LAST_CHECKIN_TIME BIGINT NOT NULL, CHECKIN_INTERVAL BIGINT NOT NULL, RECOVERER VARCHAR(80) NULL, PRIMARY KEY (INSTANCE_NAME));");
	addSql("INSERT INTO qrtz_locks values('TRIGGER_ACCESS');");
	addSql("INSERT INTO qrtz_locks values('JOB_ACCESS');");
	addSql("INSERT INTO qrtz_locks values('CALENDAR_ACCESS');");
	addSql("INSERT INTO qrtz_locks values('STATE_ACCESS');");
	addSql("INSERT INTO qrtz_locks values('MISFIRE_ACCESS');");
	}
	

	


	
	
	
	
	

	

	
}
