from .. import update_service

service = update_service.UpdateService()
#service.updateAllExchangeRates()
service.updateAllEventsFromTicketSocket()