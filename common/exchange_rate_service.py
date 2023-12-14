import os
import json
import http.client
from datetime import datetime
import time

from . import db
from common.models.exchange_rate import *

class ExchangeRateService:
    def __init__(self, exchangeRate: ExchangeRate):
        self.exchangeRate = exchangeRate

    def __getCurrentRate(self):
        url = '/rates/' + self.exchangeRate.exchangeRateSlug

        headers = {
            'Accept': 'application/json',
            'Content-type': 'application/json;charset=UTF-8',
            'x-api-key': os.getenv('STRIPE_API_KEY')
        }    

        conn = http.client.HTTPSConnection('api.striperates.com')
        conn.request('GET', url, headers=headers)
        response = conn.getresponse() 

        exchangeRate: float = 1.0
        if response.status == 200:
            jsonResponse = json.loads(response.read())
            json_data = jsonResponse['data']
            usd_rate = json_data[0]['rates']['usd']
            exchangeRate = float(usd_rate) * self.exchangeRate.multiplier
        
        return round(exchangeRate, 5)
    
    def getExchangeRateByTime(self, unixTime: int = time.time()):
        utcDateIncoming = datetime.fromtimestamp(unixTime)
		
        utci_yr = int(utcDateIncoming.strftime('%Y'))
        utci_mo = int(utcDateIncoming.strftime('%m'))
        utci_dy = int(utcDateIncoming.strftime('%d'))
        utc_incoming_midnight_time = datetime(utci_yr, utci_mo, utci_dy)
        midnightDate = utc_incoming_midnight_time.strftime('%Y-%m-%d')        

        utcDateCurrent = datetime.fromtimestamp(int(time.time()))
        utcc_yr = int(utcDateCurrent.strftime('%Y'))
        utcc_mo = int(utcDateCurrent.strftime('%m'))
        utcc_dy = int(utcDateCurrent.strftime('%d'))
        utc_current_midnight_time = datetime(utcc_yr, utcc_mo, utcc_dy)

        sql = """SELECT * FROM ExchangeRateHistory 
                 WHERE ExchangeRateId=%(exchangeRateId)s 
                 AND MidnightDate=%(midnightDate)s"""
        
        data = {
            'exchangeRateId': self.exchangeRate.exchangeRateId,
            'midnightDate': midnightDate
        }

        existingRate: float = 0
        row = db.queryOne(sql, data)
        if row != {}:
            existingRate = float(row['USDRate'])

        success: bool = True
        if existingRate == 0 or utc_incoming_midnight_time.timestamp() >= utc_current_midnight_time.timestamp():
            currentRate: float = self.__getCurrentRate()

            if existingRate == 0:
                sql2 = """INSERT INTO ExchangeRateHistory (ExchangeRateId, MidnightDate, USDRate) 
                          VALUES(%(exchangeRateId)s, %(midnightDate)s, %(currentRate)s)"""     

                data2 = {
                    'exchangeRateId': self.exchangeRate.exchangeRateId,
                    'midnightDate': midnightDate,
                    'currentRate': currentRate
                }    
                id = db.insert(sql2, data2)
                if id > 0:
                    existingRate = currentRate
            elif currentRate != existingRate:
                sql2 = """UPDATE ExchangeRateHistory SET USDRate=".$currentRate.", LastUpdated=CURRENT_TIMESTAMP 
                          WHERE ExchangeRateId=".$exchangeRateId." AND MidnightDate=".$midnightDate"""
                
                data2 = {
                    'exchangeRateId': self.exchangeRate.exchangeRateId,
                    'midnightDate': midnightDate,
                    'currentRate': currentRate
                }    
                success = db.update(sql2, data2)			
                if success:
                    existingRate = currentRate

        self.exchangeRate.usdRate = existingRate if existingRate != 0 else 1
        return self.exchangeRate