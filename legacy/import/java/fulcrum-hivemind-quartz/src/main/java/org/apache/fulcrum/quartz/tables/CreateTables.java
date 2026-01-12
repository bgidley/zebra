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

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Iterator;

public abstract class CreateTables {

	private ArrayList<String> sql = new ArrayList<String>();

	protected void addSql(String sqlCommand) {
		sql.add(sqlCommand);
	}

	public void createTables(Connection conn) throws SQLException {
		addCommands();
		Iterator<String> itr = sql.iterator();
		while (itr.hasNext()) {
			try
			{
				Statement stmt = conn.createStatement();
				String q = itr.next();
				//System.out.println(q);
				conn.setAutoCommit(true);
				stmt.execute(q);
			}
			catch (SQLException sqle)
			{
				/*
				 * ignore this if it is a table does not exist exception from
				 * postgresql or McKoi on a drop statement.
				 */
				if ((!sqle.getMessage().endsWith("does not exist")) && (!sqle.getMessage().endsWith("does not exist.")))
				{
					sqle.printStackTrace();
				}
			}
		}
		conn.setAutoCommit(false);

	}

	public abstract void addCommands();
}
