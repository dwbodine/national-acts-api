import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify
from flask_jwt import JWT, jwt_required, current_identity

sys.path.insert(0, os.path.dirname(__file__))

from common.utility import *
from common.ticket_socket_service import *
from common.event_service import *
from common.exchange_rate_service import *
from common.update_service import *
from common.migration_service import *
from common.models.user import *
from common.environment import *


user = User(1, 'user', 'password')

def authenticate(username, password):
    if username == user.username and password == user.password:
        return user

def identity(payload):
    return user

app = Flask(__name__)
application = app
loadEnv()
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

jwt = JWT(app, authenticate, identity)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin',
                         'http://localhost:4200')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization,Set-Cookie,Cookie,Cache-Control,Pragma,Expires') 
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE')

    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    return response

@app.route('/unprotected')
def unprotected():
    return jsonify({
        'message': 'This is an unprotected resource.'
    })


@app.route('/protected')
@jwt_required()
def protected():
    return jsonify({
        'message': 'This is a protected resource.',
        'current_identity': str(current_identity)
    })

@app.route('/')
def health():
   return 'All is Well\r\n'

@app.route('/account/<int:ticketSocketId>/categories')
def getCategories(ticketSocketId):
   service = TicketSocketService(ticketSocketId)
   categories = service.getCategories()
   return convertToJson(categories)

@app.route('/account/<int:ticketSocketId>/events')
def getEventsByCategoryId(ticketSocketId):
   service = TicketSocketService(ticketSocketId)
   eventCategoryId: int = None
   start: int = None
   end: int = None
   if request.args.get('eventCategoryId') != None:
      eventCategoryId = int(request.args.get('eventCategoryId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   events = service.getEventsAndOrders(eventCategoryId, start, end)
   return convertToJson(events)

@app.route('/internal/getEventsFromService')
def getEventsFromService():
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   if request.args.get('sellerId') != None:
      sellerId = int(request.args.get('sellerId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   results = service.retrieveTicketSocketEventsForUpdate(sellerId, start, end)
   return convertToJson(results)

@app.route('/internal/refreshEventsFromService/<int:sellerId>')
def refreshEventsFromService(sellerId: int = None):
   service = EventService()
   start: int = None
   end: int = None
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   
   if sellerId != None:
      results = service.refreshDatabaseFromTicketSocket(sellerId, start, end)
   else:
      results = None
   return convertToJson(results)

@app.route('/internal/updateAllEventsFromService')
def updateAllEventsFromService():
   service = UpdateService()
   results = service.updateAllEventsFromTicketSocket()
   return convertToJson(results)

@app.route('/internal/updateAllExchangeRates')
def updateAllExchangeRates():
   service = UpdateService()
   rates = service.updateAllExchangeRates()
   return convertToJson(rates)

@app.route('/internal/getAllTokens')
def getTokens():
   tokens = getAllTokens()
   return convertToJson(tokens)

@app.route('/internal/migrate/clear')
def migrationClear():
   service = MigrationService()
   result = service.clearOutNewTables()
   return convertToJson(result)

@app.route('/internal/migrate/findMissingSellers')
def findMissingSellers():
   service = MigrationService()
   missing = service.findMissingSellers()
   return convertToJson(missing)

@app.route('/internal/migrate/migrateUserSellers')
def migrateSellers():
   service = MigrationService()
   result = service.migrateSellers()
   return convertToJson(result)

@app.route('/internal/migrate/migrateExternalEvents')
def migrateExternalEvents():
   service = MigrationService()
   result = service.migrateExternalEvents()
   return convertToJson(result)

@app.route('/internal/migrate/migrateEventsAndOrders')
def migrateEventsAndOrders():
   service = MigrationService()
   results = service.migrateEventData()
   return convertToJson(results)


if __name__ == "__main__":
    app.run()
