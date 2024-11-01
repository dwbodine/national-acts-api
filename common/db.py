"""
Uniform database accessor utility
"""

import os
import mysql.connector
import mysql.connector.connection


def db_get_connection():
    """
    Connect to MySql database
    """
    return mysql.connector.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_DB"),
        connection_timeout=3600,
    )


def db_query_all(sql: str, json_data=None, cnx=None):
    """
    Return multiple rows
    """
    rows = []
    keep_alive = True

    if cnx is None:
        cnx = db_get_connection()
        keep_alive = False

    cursor = cnx.cursor()

    if json_data is not None:
        cursor.execute(sql, json_data)
    else:
        cursor.execute(sql)

    cursor_rows = cursor.fetchall()
    for cursor_row in cursor_rows:
        row = __convert_cursor_row_to_dictionary(cursor_row, cursor)
        rows.append(row)

    cursor.close()

    if keep_alive is False:
        cnx.close()

    return rows


def db_query_one(sql: str, json_data, cnx=None):
    """
    Query for single result
    """
    row = {}
    keep_alive = True

    if cnx is None:
        cnx = db_get_connection()
        keep_alive = False

    cursor = cnx.cursor()

    cursor.execute(sql, json_data)

    cursor_row = cursor.fetchone()
    if cursor_row is not None:
        row = __convert_cursor_row_to_dictionary(cursor_row, cursor)

    cursor.close()

    if keep_alive is False:
        cnx.close()

    return row


def __convert_cursor_row_to_dictionary(cursor_row: any, cursor: any):
    """
    to get around the Python MySQL limitation of using integers as indices,
    this converts the row tuples to dictionary objects that can be used
    as associative arrays by the code
    """
    row = {}
    counter: int = 0
    for column in cursor.description:
        field: str = column[0]
        row[field] = cursor_row[counter]
        counter += 1
    return row


def db_update(sql: str, json_data=None, cnx=None):
    """
    Update SQL database
    """
    keep_alive = True

    if cnx is None:
        cnx = db_get_connection()
        keep_alive = False

    cursor = cnx.cursor()

    if json_data is not None:
        cursor.execute(sql, json_data)
    else:
        cursor.execute(sql)

    count = cursor.rowcount

    cnx.commit()

    cursor.close()

    if keep_alive is False:
        cnx.close()

    return count > 0


def db_insert(sql: str, json_data=None, cnx=None):
    """
    Insert to MySQL table
    """
    keep_alive = True

    if cnx is None:
        cnx = db_get_connection()
        keep_alive = False

    cursor = cnx.cursor()

    if json_data is not None:
        cursor.execute(sql, json_data)
    else:
        cursor.execute(sql)

    cnx.commit()

    new_id = cursor.lastrowid

    cursor.close()

    if keep_alive is False:
        cnx.close()

    return new_id


def db_delete(sql: str, json_data=None, cnx=None):
    """
    Delete row from MySQL table
    """
    keep_alive = True

    if cnx is None:
        cnx = db_get_connection()
        keep_alive = False

    cursor = cnx.cursor()

    if json_data is not None:
        cursor.execute(sql, json_data)
    else:
        cursor.execute(sql)

    count = cursor.rowcount

    cnx.commit()

    cursor.close()

    if keep_alive is False:
        cnx.close()

    return count > 0


def db_convert_list_to_parameters(the_list: list[any], param_object: dict, prefix: str):
    """
    SQL safe method to convert Python list to parameterized list
    """
    sql = "("
    counter = 0
    for item in the_list:
        if counter > 0:
            sql += ", "
        param_name = prefix + "_" + str(counter)
        sql += "%(" + param_name + ")s"
        param_object[param_name] = item
        counter += 1
    sql += ")"
    return sql
