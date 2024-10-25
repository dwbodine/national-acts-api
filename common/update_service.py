import time
from . import db
from . import exchange_rate_service
from . import event_service
from . import utility

class UpdateService:
    def updateAllExchangeRates(self):
        rates: list[exchange_rate_service.ExchangeRate] = []
        sql = "select * from ExchangeRates"
        rows = db.queryAll(sql)
        for row in rows:
            service = exchange_rate_service.ExchangeRateService(exchange_rate_service.ExchangeRate(int(row['ExchangeRateId']), row['ServiceTokenId'], float(row['Multiplier'])))
            rate = service.getExchangeRateByTime()
            rates.append(rate)
        return rates

    def updateAllEventsFromTicketSocket(self):
        service = event_service.EventService()
        results = service.refreshDatabaseFromTicketSocket()
        if results != None and results.succeeded == True:
            results = service.updateDailyOrderData(results)
            
        return results
    
    def migrateTicketTypeIds(self):
        success: bool = True
        sql = """SELECT TicketSocketEventId, TicketSocketTicketTypeId, TicketTypeName 
                    FROM TicketSocketTicketTypes 
                    ORDER BY TicketSocketEventId, TicketSocketTicketTypeId"""
        rows = db.queryAll(sql)
        for row in rows:
            ticketSocketEventId = int(row["TicketSocketEventId"])
            eventTicketTypeId = int(row["TicketSocketTicketTypeId"])
            eventTicketTypeName = str(row["TicketTypeName"]).upper()
            orderTicketSql = """SELECT TicketSocketOrderTickets.Id, TicketSocketOrderTickets.TicketType 
                                    FROM TicketSocketOrderTickets 
                                    JOIN TicketSocketOrders ON TicketSocketOrders.Id = TicketSocketOrderTickets.TicketSocketOrderId 
                                    WHERE TicketSocketOrders.TicketSocketEventId = %(ticketSocketEventId)s"""
            orderTicketData = {
                'ticketSocketEventId': ticketSocketEventId
            }
            orderTicketRows = db.queryAll(orderTicketSql, orderTicketData)
            if len(orderTicketRows) == 0:
                continue
            for orderTicketRow in orderTicketRows:
                ticketId = int(orderTicketRow["Id"])
                ticketType = str(orderTicketRow["TicketType"]).upper()
                if ticketType == eventTicketTypeName:
                    updateSql = """UPDATE TicketSocketOrderTickets SET TicketSocketTicketTypeId=%(eventTicketTypeId)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketId)s"""
                    udpateData = {
                        'eventTicketTypeId': eventTicketTypeId,
                        'ticketId': ticketId
                    }
                    success = db.update(updateSql, udpateData)
                if success != True: 
                    break
            if success != True: 
                break
        return success
    
    def migrateAttendeeNames(self):
        sql = """SELECT Id, AttendeeNames, PurchaserFirstName, PurchaserLastName FROM TicketSocketOrders WHERE COALESCE(AttendeeNames, '') <> ''"""
        rows = db.queryAll(sql)
        success: bool = True
        for row in rows:
            orderId = int(row["Id"])
            attendeeNameStr = str(row["AttendeeNames"]).strip()
            purchaserFirstName = str(row["PurchaserFirstName"]).strip()
            purchaserLastName = str(row["PurchaserLastName"]).strip()
            ticketSql = """SELECT Id FROM TicketSocketOrderTickets WHERE TicketSocketOrderId=%(orderId)s"""
            ticketData = {
                'orderId': orderId
            }
            attendeeNames = attendeeNameStr.split('/')
            ticketRows = db.queryAll(ticketSql, ticketData)
            i: int = 0
            for ticketRow in ticketRows:
                ticketId = int(ticketRow["Id"])
                attendeeFirstName: str = ''
                attendeeLastName: str = ''
                if i < len(attendeeNames):
                    aNameStr = attendeeNames[i].strip()
                    aNameStr = ' '.join(aNameStr.split())
                    aNameStr = aNameStr.strip()
                    if len(aNameStr) > 0:
                        aName = aNameStr.split(' ')
                        if len(aName) > 0:
                            attendeeFirstName = aName[0].strip()
                            if len(attendeeFirstName) == 0:
                                attendeeFirstName = purchaserFirstName
                                attendeeLastName = purchaserLastName
                            elif len(aName) > 1:
                                attendeeLastName = aName[1].strip()
                    else:
                        attendeeFirstName = purchaserFirstName
                        attendeeLastName = purchaserLastName
                else:
                    attendeeFirstName = purchaserFirstName
                    attendeeLastName = purchaserLastName
                ticketUpdateSql = """UPDATE TicketSocketOrderTickets SET AttendeeFirstName=%(attendeeFirstName)s, AttendeeLastName=%(attendeeLastName)s, LastUpdate=CURRENT_TIMESTAMP WHERE Id=%(ticketId)s"""
                ticketUpdateData = {
                    'ticketId': ticketId, 
                    'attendeeFirstName': attendeeFirstName, 
                    'attendeeLastName': attendeeLastName
                }
                success = db.update(ticketUpdateSql, ticketUpdateData)
                if success != True:
                    break
                i += 1
            if success != True:
                break
        return success