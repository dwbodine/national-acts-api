import os
import sys
from datetime import timedelta
from flask import Flask, request, jsonify
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, unset_jwt_cookies, jwt_required, JWTManager

sys.path.insert(0, os.path.dirname(__file__))

from common.utility import *
from common.ticket_socket_service import *
from common.event_service import *
from common.exchange_rate_service import *
from common.update_service import *
from common.seller_service import *
from common.environment import *

# loads environment variables in debug mode
loadEnv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv('SECRET_KEY')
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
jwt = JWTManager(app)
application = app

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin',
                         '*')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization,Set-Cookie,Cookie,Cache-Control,Pragma,Expires') 
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE')

    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    return response

@app.route('/')
def health():
   return 'All is Well\r\n'

@app.route('/token', methods=["POST"])
def create_token():
    email = request.json.get("email", None)
    password = request.json.get("password", None)
    
    if email == None or password == None:
        return {"msg", "Bad request"}, 400
    
    user = User()
    user.authenticate(email, password)
    if user.isAuthenticated != True:
        return {"msg": "Wrong email or password"}, 401

    access_token = create_access_token(identity=email)
    response = {"access_token":access_token}
    return convertToJson(response)

@app.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response

@app.route('/profile')
def my_profile():
    response_body = {
        "name": "Nagato",
        "about" :"Hello! I'm a full stack developer that loves python and javascript"
    }

    return response_body

@app.route("/sendPasswordReset", methods=["POST"])
def sendPasswordReset():
   email = request.json.get("email", None)
   if email == None:
      return {"msg", "Bad request"}, 400
   user = User()
   success = user.sendPasswordResetEmail(email)
   return convertToJson(success)
   
@app.route("/validateResetCode", methods=["POST"])
def validateResetCode():
   userId = request.json.get("userId", None)
   code = request.json.get("code", None)
   if userId == None or code == None:
      return {"msg", "Bad request"}, 400
   user = User()
   success = user.validatePasswordResetCode(int(userId), int(code))
   return convertToJson(success)

@app.route("/setPassword", methods=["POST"])
def resetPassword():
   userId = request.json.get("userId", None)
   password = request.json.get("password", None)
   confirmPassword = request.json.get("confirmPassword", None)
   user = User()
   if userId == None or password == None or confirmPassword == None:
      return {"msg", "Bad request"}, 400
   error = user.validatePassword(password, confirmPassword)
   if error != None:
      return {"msg", error}, 400
   return None   

@app.route('/events')
def getEvents():
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   excludeStart: int = None
   excludeEnd: int = None
   searchTerm: str = None
   showInactive: bool = False
   tsEventId: int = None
   if request.args.get('sellerId') != None:
      sellerId = int(request.args.get('sellerId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   if request.args.get('excludeStart') != None:
      excludeStart = int(request.args.get('excludeStart'))
   if request.args.get('excludeEnd') != None:
      excludeEnd = int(request.args.get('excludeEnd'))
   if request.args.get('inactive') != None:
      showInactive = True if int(request.args.get('inactive')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))   
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   results = service.getEventsAndOrders(False, sellerId, start, end, showInactive, searchTerm, tsEventId, excludeStart, excludeEnd)
   return convertToJson(results)

@app.route('/eventsAndOrders')
def getEventsAndOrders():
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   searchTerm: str = None
   showInactive: bool = False
   tsEventId: int = None
   if request.args.get('sellerId') != None:
      sellerId = int(request.args.get('sellerId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   if request.args.get('inactive') != None:
      showInactive = True if int(request.args.get('inactive')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId)
   return convertToJson(results)

@app.route('/sellers/<int:userId>')
def getUserSellers(userId: int):
   service = SellerService()
   results = service.getUserSellers(userId)
   return convertToJson(results)

@app.route('/internal/getEventsFromService/<int:sellerId>')
def getEventsFromService(sellerId: int = None):
   service = EventService()
   start: int = None
   end: int = None
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   
   if sellerId != None:
      results = service.retrieveTicketSocketEventsForUpdate(sellerId, start, end)
   else:
      results = None
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
      # currently hard-coded to TJ as updater
      results = service.refreshDatabaseFromTicketSocket(sellerId, start, end, 5)
   else:
      results = None
   return convertToJson(results)

@app.route('/internal/accounts')
def getAccounts():
   accounts = getAllAccounts()
   return convertToJson(accounts)

@app.route('/internal/<int:ticketSocketId>/categories')
def getCategories(ticketSocketId):
   service = TicketSocketService(ticketSocketId)
   categories = service.getCategories()
   return convertToJson(categories)

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

@app.route('/internal/getUpdateHistory')
def getUpdateHistory():
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   userId: int = None
   limit: int = None
   if request.args.get('sellerId') != None:
      sellerId = int(request.args.get('sellerId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   if request.args.get('userId') != None:
      userId = int(request.args.get('userId'))
   if request.args.get('limit') != None:
      limit = int(request.args.get('limit'))

   logs = service.getTicketSocketRefreshHistory(sellerId, start, end, userId, limit)
   return convertToJson(logs)

if __name__ == "__main__":
    app.run()
