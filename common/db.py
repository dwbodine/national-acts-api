import os
import mysql.connector

def __getDbConnection():
    return mysql.connector.connect(user=os.getenv('DB_USER'), 
                                   password=os.getenv('DB_PASSWORD'),
                                   host=os.getenv('DB_HOST'),
                                   database=os.getenv('DB_DB'))

def queryAll(sql: str, jsonData = None):    
    rows = []
    cnx = __getDbConnection()
    cursor = cnx.cursor()

    if jsonData != None:
        cursor.execute(sql, jsonData)
    else:
        cursor.execute(sql)

    cursorRows = cursor.fetchall()
    for cursorRow in cursorRows:
        row = __convertCursorRowToDictionary(cursorRow, cursor)
        rows.append(row)

    cursor.close()
    cnx.close()

    return rows

def queryOne(sql: str, jsonData):    
    row = {}
    cnx = __getDbConnection()
    cursor = cnx.cursor()

    cursor.execute(sql, jsonData)

    cursorRow = cursor.fetchone()
    if cursorRow != None:
        row = __convertCursorRowToDictionary(cursorRow, cursor)

    cursor.close()
    cnx.close()

    return row


def __convertCursorRowToDictionary(cursorRow: any, cursor: any):
    # to get around the Python MySQL limitation of using integers as indices,
    # this converts the row tuples to dictionary objects that can be used
    # as associative arrays by the code
    row = {}
    counter: int = 0
    for column in cursor.description:
        field: str = column[0]
        row[field] = cursorRow[counter]
        counter += 1
    return row


def update(sql: str, jsonData = None):
    cnx = __getDbConnection()
    cursor = cnx.cursor()
        
    if jsonData != None:
        cursor.execute(sql, jsonData)
    else:
        cursor.execute(sql)
    
    count = cursor.rowcount

    cnx.commit()

    cursor.close()
    cnx.close()

    return count > 0

def insert(sql: str, jsonData = None):
    cnx = __getDbConnection()
    cursor = cnx.cursor()
        
    if jsonData != None:
        cursor.execute(sql, jsonData)
    else:
        cursor.execute(sql)
    
    cnx.commit()

    newId = cursor.lastrowid

    cursor.close()
    cnx.close()

    return newId

def delete(sql: str, jsonData = None):
    cnx = __getDbConnection()
    cursor = cnx.cursor()
        
    if jsonData != None:
        cursor.execute(sql, jsonData)
    else:
        cursor.execute(sql)
    
    count = cursor.rowcount

    cnx.commit()

    cursor.close()
    cnx.close()

    return count > 0

def convertListToParameters(theList: list[any], paramObject: dict, prefix: str):
    sql = '('
    counter = 0
    for item in theList:
        if counter > 0:
            sql += ', '
        paramName = prefix + '_' + str(counter)
        sql += '%(' + paramName + ')s'
        paramObject[paramName] = item
        counter += 1
    sql += ')'
    return sql