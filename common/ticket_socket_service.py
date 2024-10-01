import os
import json
import http.client
import time
from datetime import datetime
from typing import Any

from . import utility
from . import db
from common.models.ticket_socket import *

class TicketSocketService:
    name: str = ''
    serviceUrl: str = ''
    utcOffsetHours: int = 0
    exchangeRateId: int = 1
    exchangeRateSlug: str = ''
    mulitiplier: float = 1
    currencySymbol: str = ''
    token: str = ''
    categories: list[TicketSocketCategory] = []
    events: list[TicketSocketEvent] = []

    def __init__(self, ticketSocketId: int):
        self.ticketSocketId = ticketSocketId
        self.__initialize()

    def __getTsAccountData(self):
        sql = """SELECT TicketSocket.AccountName, TicketSocket.ServiceUrl, TicketSocket.DefaultUtcOffsetHours, TicketSocket.ExchangeRateId,  
                 ExchangeRates.Symbol, ExchangeRates.ServiceTokenId, ExchangeRates.Multiplier 
                 FROM TicketSocket 
                 INNER JOIN ExchangeRates ON ExchangeRates.ExchangeRateId = TicketSocket.ExchangeRateId
                 WHERE TicketSocketId=%(ts_id)s"""

        data = {
            'ts_id': self.ticketSocketId
        }

        row = db.queryOne(sql, data)
        if row != {}:
            self.name = row['AccountName']
            self.serviceUrl = row['ServiceUrl']
            self.serviceUrl = self.serviceUrl.replace('https://', '')
            self.utcOffsetHours = int(row['DefaultUtcOffsetHours'])
            self.currencySymbol = row['Symbol']
            self.exchangeRateId = int(row['ExchangeRateId'])
            self.exchangeRateSlug = row['ServiceTokenId']
            self.mulitiplier = float(row['Multiplier'])        

    def __getJwtToken(self):
        uid = os.getenv('API_UID_'+str(self.ticketSocketId))
        pwd = os.getenv('API_PWD_'+str(self.ticketSocketId))
        pk = os.getenv('API_PK_'+str(self.ticketSocketId))
        pk_slug = os.getenv('API_PK_SLUG_'+str(self.ticketSocketId))

        creds = {
            "userName": uid,
            "password": pwd,
            "publicKey": pk,
            "publicKeySlug": pk_slug
        }

        url = '/api/v1/tokens'
        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8'
        }    

        conn = http.client.HTTPSConnection(self.serviceUrl)
        conn.request('POST', url, json.dumps(creds), headers)
        response = conn.getresponse()    
        
        jwt = ''
        if response.status == 200:
            jsonResponse = json.loads(response.read())
            jwt = jsonResponse['data']['jwt']
        
        conn.close()
        self.token = jwt

    def __initialize(self):
        self.__getTsAccountData()
        self.__getJwtToken()

    def getCategories(self):
        url = '/api/v1/categories'
        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8',
            'Authorization': 'Bearer ' + self.token
        }    

        conn = http.client.HTTPSConnection(self.serviceUrl)
        conn.request('GET', url, headers=headers)
        response = conn.getresponse()    
        
        self.categories = []
        if response.status == 200:
            jsonResponse = json.loads(response.read())
            jsonData = jsonResponse['data']
            for item in jsonData:
                categoryId: int = 0
                title: str = ''
                if 'id' in item:
                    categoryId = int(item['id'])
                if 'title' in item:
                    title = item['title']
                if categoryId > 0 and title != '':
                    self.categories.append(TicketSocketCategory(item['id'], item['title']))            
        
        conn.close()

        return self.categories
    
    def getEventsAndOrders(self, eventCategoryId: int = None, unixStart: int = None, unixEnd: int = None):
        url = '/api/v1/events?includeEnded=true&includeOffSale=true&includeTicketTypes=true&limit=9999'

        if eventCategoryId != None and eventCategoryId > 0:
            url += '&category=' + str(eventCategoryId)
            
        if unixStart == None and unixEnd == None:
            url += "&startsAfter=" + str(int(time.time()))
        else:
            if unixStart != None:
                url += "&startsAfter=" + str(unixStart)
            if unixEnd != None:
                url += "&startsBefore=" + str(unixEnd)
                
        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8',
            'Authorization': 'Bearer ' + self.token
        }    

        conn = http.client.HTTPSConnection(self.serviceUrl, timeout=600)
        conn.request('GET', url, headers=headers)
        response = conn.getresponse() 

        self.events = []
        if response.status == 200:
            jsonResponse = json.loads(response.read())
            jsonData = jsonResponse['data']
            for item in jsonData:
                # basic info
                id: int = 0
                title: str = ''
                if 'id' in item:
                    id = int(item['id'])
                if 'title' in item:
                    title = item['title']

                if id == 0 or title == '':
                    continue

                event = TicketSocketEvent(id, title)

                onSale: str = ''
                if 'onsale' in item:
                    onSale = item['onsale']
                event.onSale = True if onSale == '1' else False

                categories = []
                if 'categories' in item:
                    categories = item['categories']

                if len(categories) <= 0:
                    continue

                category = categories[0]

                categoryId: int = 0
                if 'id' in category:
                    categoryId = int(category['id'])

                if categoryId <= 0:
                    continue
                
                event.eventCategoryId = categoryId

                thumbnail: str = ''
                if 'smallPic' in item:
                    thumbnail = item['smallPic']
                event.thumbnail = thumbnail

                sefUrl: str = ''
                if 'sefUrl' in item:
                    sefUrl = item['sefUrl']

                event.ticketSocketUrl = "https://" + self.serviceUrl + "/event/" + sefUrl

                # venue info
                venue = ''
                if 'venue' in item:
                    venue = utility.fixMagicQuotes(item['venue'])

                customFields = {}
                if 'customFields' in item:
                    customFields = item['customFields']

                address1 = ''                
                if 'venueAddress1' in item and item['venueAddress1'] != '':
                    address1 = utility.fixMagicQuotes(item['venueAddress1'])
                elif customFields != {} and 'venueAddress1' in customFields:
                    address1 = utility.fixMagicQuotes(customFields['venueAddress1'])

                address2 = ''
                if 'venueAddress2' in item and item['venueAddress2'] != '':
                    address2 = utility.fixMagicQuotes(item['venueAddress2'])
                elif customFields != {} and 'venueAddress2' in customFields:
                    address2 = utility.fixMagicQuotes(customFields['venueAddress2'])

                city = ''
                if 'venueCity' in item and item['venueCity'] != '':
                    city = utility.fixMagicQuotes(item['venueCity'])
                elif customFields != {} and 'venueCity' in customFields:
                    city = utility.fixMagicQuotes(customFields['venueCity'])

                state = ''
                if 'venueState' in item and item['venueState'] != '':
                    state = utility.fixMagicQuotes(item['venueState'])
                elif customFields != {} and 'venueState' in customFields:
                    state = utility.fixMagicQuotes(customFields['venueState'])

                zip = ''
                if 'venuePostalCode' in item and item['venuePostalCode'] != '':
                    zip = utility.fixMagicQuotes(item['venuePostalCode'])
                elif customFields != {} and 'venuePostalCode' in customFields:
                    zip = utility.fixMagicQuotes(customFields['venuePostalCode'])

                country = ''
                if 'venueCountry' in item and item['venueCountry'] != '':
                    country = utility.fixMagicQuotes(item['venueCountry'])
                elif customFields != {} and 'venueCountry' in customFields:
                    country = utility.fixMagicQuotes(customFields['venueCountry'])
                    
                formatPhones: bool = True
                if country != '' and country != 'USA' and country != 'United States':
                    formatPhones = False

                timezone = ''
                if customFields != {} and 'timezone' in customFields:
                    timezone = customFields['timezone']
                
                event.venue = TicketSocketVenue(venue, address1, address2, city, state, zip, country, timezone)
                
                # date/time info
                displayDate: str = ''
                if 'displayStartDate' in item:
                    displayDate = item['displayStartDate']

                event.displayDate = displayDate

                eventUtc: int = 0
                if 'start' in item:
                    eventUtc = int(item['start'])

                event.utcTime = eventUtc

                # need at least one of them to be non-zero
                if displayDate == '' and eventUtc == 0:
                    continue

                # note: this is a total hack since TicketSocket returns in UTC
                # BUT does NOT return a reliable timezone value for the venue (yeah this is that bad - even when it's right, 
                # it's a timezone that isn't convertible using Python or well...anything)
                # So what we do instead is define a "default offset" in the database that roughly gets us the right date
                # since we're not displaying times in the front end.  With any luck the "displayStartDate" comes back 
                # with a valid value and we use that for our date instead         

                try:
                    eventDt = datetime.strptime(event.displayDate, '%m/%d/%Y')
                    event.eventDate = eventDt.strftime('%Y-%m-%d')
                except:
                    eventTime: int = event.utcTime + (self.utcOffsetHours * 60 * 60)         
                    event.eventDate = datetime.fromtimestamp(eventTime).strftime('%Y-%m-%d')
                    
                    
                # ticket types
                ticketTypes = []
                if 'ticketTypes' in item:
                    ticketTypes = self.getTicketTypesFromEvent(item['ticketTypes'])
                event.ticketTypes = ticketTypes                

                # orders
                event.orders = self.getOrdersFromEventId(event.id, formatPhones)       
                
                self.events.append(event)

        return self.events
    
    def getTicketTypesFromEvent(self, ticketTypes: list[Any]):
        if len(ticketTypes) <= 0:
            return []
        
        ttypes: list[TicketSocketTicketType] = []
        for item in ticketTypes:
            id = int(item['id'])
            name = str(item['name'])
            eventId = int(item['eventId'])
            totalAvailable = int(item['quantity'])
            isActive: bool = True
            if 'deleted' in item:
                isActive = (int(item['deleted']) == 0)
            ttype = TicketSocketTicketType(eventId, id, name, totalAvailable, isActive)
            ttypes.append(ttype)
            
        return ttypes
    
    def getOrdersFromEventId(self, eventId: int, formatPhoneNumbers: bool):
        # get list of orderIds first
        orderIds = self.getOrderIdsFromEventId(eventId)

        # if there are no orders, return nothing
        if len(orderIds) <= 0:
            return []

        # common service settings
        baseUrl: str = '/api/v1/orders/'
        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8',
            'Authorization': 'Bearer ' + self.token
        } 
        conn = http.client.HTTPSConnection(self.serviceUrl, timeout=600)

        # loop through and append orders
        orders = []
        for orderId in orderIds:
            url = baseUrl + str(orderId)
            conn.request('GET', url, headers=headers)
            response = conn.getresponse() 

            if response.status == 200:
                jsonResponse = json.loads(response.read())
                jsonData = jsonResponse['data']
                # get data from order
                id: int = 0
                if 'id' in jsonData:
                    id = int(jsonData['id'])

                if id == 0:
                    continue

                order = TicketSocketOrder(id, eventId)

                if 'cancelled' in jsonData:
                    order.cancelled = bool(jsonData['cancelled'])

                if 'deleted' in jsonData:
                    order.deleted = True if int(jsonData['deleted']) == 1 else False

                tickets = None
                if 'tickets' in jsonData:
                    tickets = jsonData['tickets']

                numTickets: int = 0
                totalCount: int = 0
                if tickets != None:        
                    if 'totalCount' in tickets:
                        totalCount = int(tickets['totalCount'])

                orderRevenue: float = 0
                orderServiceFees: float = 0
                orderTickets = []
                orderAttendeeNames = []
                orderShirts = []
                if totalCount > 0:
                    ticketData = tickets['data']
                    for item in ticketData:
                        # if the ticket doesn't belong to this event, move along
                        # and yes that happens that an order can contain tickets to multiple events

                        itemEventId: int = 0
                        if 'eventId' in item:
                            itemEventId = int(item['eventId'])
                        if itemEventId != int(eventId):
                            continue
                        
                        numTickets += 1

                        # set properties on order from ticket data if not present
                        if order.userId == 0 and 'userId' in item:
                            order.userId = int(item['userId'])
                        if order.purchaserFirstName == '' and 'billing_firstName' in item:
                            order.purchaserFirstName = utility.fixMagicQuotes(item['billing_firstName'])
                        if order.purchaserLastName == '' and 'billing_lastName' in item:
                            order.purchaserLastName = utility.fixMagicQuotes(item['billing_lastName'])
                        if order.purchaserCity == None and 'billing_city' in item:
                            order.purchaserCity = utility.fixMagicQuotes(item['billing_city'])
                        if order.purchaserState == None and 'billing_state' in item:
                            order.purchaserState = utility.fixMagicQuotes(item['billing_state'])
                        if order.purchaserZipCode == None and 'billing_zip' in item:
                            order.purchaserZipCode = utility.fixMagicQuotes(item['billing_zip'])
                        if order.purchaserCountry == None and 'billing_country' in item:
                            order.purchaserCountry = utility.fixMagicQuotes(item['billing_country'])
                        if order.purchaserIpAddress == None and 'remoteAddr' in item:
                            order.purchaserIpAddress = utility.fixMagicQuotes(item['remoteAddr'])
                        if order.purchaseDate == '' and 'purchaseDate' in item:
                            # datetime is not serializable in python, convert it to ISO-compatible string
                            purchaseDate = datetime.fromtimestamp(float(item['purchaseDate']))
                            order.purchaseDate = purchaseDate.strftime('%Y-%m-%d')
                            order.purchaseTimestamp = purchaseDate.strftime('%Y-%m-%d %H:%M:%S')
                        if order.email == '' and 'email' in item:
                            order.email = item['email']
                        
                        # add attendee data from ticket
                        attendeeName: str = ''
                        if 'partyMember' in item:
                            attendeeName = utility.fixMagicQuotes(item['partyMember'])
                            if 'partyMemberLastName' in item:
                                attendeeName += ' ' + utility.fixMagicQuotes(item['partyMemberLastName'])

                        if attendeeName != '':
                            orderAttendeeNames.append(attendeeName)

                        # get shirt and phone data from questions    
                        purchaserQuestions: list = []
                        attendeeQuestions: list = []
                        if 'purchaserQuestions' in item:                    
                            purchaserQuestions = list(item['purchaserQuestions'])
                        if 'attendeeQuestions' in item:
                            attendeeQuestions = list(item['attendeeQuestions'])
                        questions = purchaserQuestions + attendeeQuestions
                        if len(questions) > 0:
                            for questionItem in questions:
                                question: str = ''
                                if 'question' in questionItem:
                                    question = str(questionItem['question']).lower()

                                if question == '':
                                    continue

                                answer: str = ''
                                if 'answerText' in questionItem:
                                    answer = str(questionItem['answerText'])
                                    
                                if answer != '':
                                    if question.find('phone') >= 0 and order.phone == '':
                                        if formatPhoneNumbers:
                                            order.phone = utility.formatPhone(answer)
                                        else:
                                            order.phone = answer
                                    elif question.find('shirt') >= 0:
                                        orderShirts.append(answer)

                        # create the ticket object
                        price: float = 0
                        if 'price' in item:
                            price = float(item['price'])

                        ticketId: int = 0
                        if 'id' in item:
                            ticketId = int(item['id'])
                        ticketType: str = ''
                        if 'ticketTypeName' in item:
                            ticketType = item['ticketTypeName']
                        serviceFee: float = 0
                        if 'fee1Amount' in item:
                            serviceFee = float(item['fee1Amount'])
                        ticketTypeId: int = 0
                        if 'typeId' in item:
                            ticketTypeId = int(item['typeId'])
                        barcode: str = ''
                        if 'barcode' in item:
                            barcode = str(item['barcode'])
                        availableScans: int = 0
                        if 'availableScans' in item:
                            availableScans = int(item['availableScans'])
                        purchaseLocation: str = ''
                        if 'purchaseLocation' in item:
                            purchaseLocation = str(item['purchaseLocation'])
                        scannedTimestamp: int = 0
                        if 'scannedTimestamp' in item:
                            scannedTimestamp = int(item['scannedTimestamp'])

                        if ticketId == 0 or ticketType == '':
                            continue
                        
                        ticket = TicketSocketTicket(ticketId, ticketType, price, serviceFee, ticketTypeId, barcode, availableScans, purchaseLocation, scannedTimestamp)
                        orderTickets.append(ticket)

                        orderRevenue += price
                        orderServiceFees += serviceFee

                if len(orderTickets) > 0:
                    order.numTickets = numTickets
                    order.tickets = orderTickets
                    order.shirts = orderShirts
                    order.attendeeNames = orderAttendeeNames
                    order.revenue = orderRevenue
                    order.serviceFees = orderServiceFees

                    orders.append(order)

        return orders
    
    def getOrderIdsFromEventId(self, eventId: int):
        url = '/api/v1/orders?limit=999&eventId=' + str(eventId)

        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8',
            'Authorization': 'Bearer ' + self.token
        }    

        conn = http.client.HTTPSConnection(self.serviceUrl, timeout=600)
        conn.request('GET', url, headers=headers)
        response = conn.getresponse() 

        orderIds: list[int] = []
        if response.status == 200:
            jsonResponse = json.loads(response.read())
            json_data = jsonResponse['data']
            for item in json_data:
                orderId: int = 0
                if 'orderId' in item:
                    orderId = int(item['orderId'])
                if orderId != 0:
                    orderIds.append(orderId)
        
        return orderIds
    
def getAllAccounts():
    accounts: list[TicketSocketService] = []
    sql = "SELECT TicketSocketId FROM TicketSocket ORDER BY TicketSocketId"
    rows = db.queryAll(sql)
    for row in rows:
        ticketSocketId = int(row["TicketSocketId"])
        account = TicketSocketService(ticketSocketId)
        accounts.append(account)
    return accounts