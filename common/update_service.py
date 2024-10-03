import time
from . import db
from . import exchange_rate_service
from . import event_service

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
            timer: float = time.time()
            duration: float = 0
            success = service.updateDailyOrderData()
            duration = time.time() - timer
            results.setOrderUpdateSuccess(success, duration)
        return results