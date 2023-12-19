import os
import sys
from datetime import timedelta, timezone
from flask import Flask, request, jsonify
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, verify_jwt_in_request, unset_jwt_cookies, jwt_required, JWTManager

sys.path.insert(0, os.path.dirname(__file__))

from common.utility import *
from common.ticket_socket_service import *
from common.event_service import *
from common.exchange_rate_service import *
from common.update_service import *
from common.seller_service import *
from common.user_service import *
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
                         'Content-Type,Authorization,Set-Cookie,Cookie,Cache-Control,Pragma,Expires,x-api-key') 
   response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE,OPTIONS')

   response.cache_control.no_cache = True
   response.cache_control.no_store = True
   response.cache_control.must_revalidate = True
    
   try:
      # put this line here to prevent exceptions when there is no auth header
      if request.headers.get("Authorization") != None:
         exp_timestamp = get_jwt()["exp"]
         now = datetime.now(timezone.utc)
         target_timestamp = datetime.timestamp(now + timedelta(minutes=30))
         if target_timestamp > exp_timestamp:
            access_token = create_access_token(identity=get_jwt_identity())
            data = response.get_json()
            if type(data) is dict:
               data["access_token"] = access_token 
               response.data = json.dumps(data)
   except (RuntimeError, KeyError):
      # Case where there is not a valid JWT. Just return the original respone
      print('JWT not found')
   return response

@app.route('/')
def health():
   return 'All is Well\r\n'

@app.route('/internal/mail', methods=["POST"])
def sendMail():
   # secured by mail api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('MAIL_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   toEmail = request.json.get("toEmail", None)
   toName = request.json.get("toName", None)
   subject = request.json.get("subject", None)
   htmlContent = request.json.get("htmlContent", None)
   ccEmails = request.json.get("ccEmails", None)
   
   if toEmail == None or toEmail == "" or subject == None or subject == "" or htmlContent == None or htmlContent == "":
      return {"msg": "Bad Request"}, 200   
   
   result = utility.sendEmail(toEmail, subject, htmlContent, toName, ccEmails)
           
   return convertToJson(result)

@app.route('/user/login', methods=["POST"])
def create_token():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   username = request.json.get("username", None)
   password = request.json.get("password", None)
    
   if username == None or password == None:
      return {"msg", "Bad request"}, 400
    
   service = UserService()
   loginResponse = service.login(username, password)
    
   if loginResponse.errorMessage != None:
      return {"msg": loginResponse.errorMessage}, 401
   elif loginResponse.user == None or loginResponse.user.isAuthenticated != True:
      return {"msg": "Invalid username or password"}, 401    
    
   access_token = create_access_token(identity=username)
   response = {"access_token": access_token}
   return convertToJson(response)

@app.route("/user/logout", methods=["POST"])
def logout():
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response

@app.route('/user/profile')
@jwt_required()
def my_profile():
    response_body = {
        "name": "Nagato",
        "about" :"Hello! I'm a full stack developer that loves python and javascript"
    }

    return response_body

@app.route("/user/sendPasswordReset", methods=["POST"])
def sendPasswordReset():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   username = request.json.get("username", None)
   if username == None:
      return {"msg", "Bad request"}, 400
   service = UserService()
   success = service.sendPasswordResetEmail(username)
   return convertToJson(success)
   
@app.route("/user/validateResetCode", methods=["POST"])
def validateResetCode():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   username = request.json.get("username", None)
   code = request.json.get("code", None)
   if username == None or code == None:
      return {"msg", "Bad request"}, 400
   service = UserService()
   success = service.validatePasswordResetCode(str(username), int(code))
   return convertToJson(success)

@app.route("/user/resetPassword", methods=["POST"])
def resetPassword():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   username = request.json.get("username", None)
   password = request.json.get("password", None)
   confirmPassword = request.json.get("confirmPassword", None)
   code = request.json.get("code", None)
   service = UserService()
   if username == None or password == None or confirmPassword == None or code == None:
      return {"msg", "Bad request"}, 400
   result = service.resetPassword(username, code, password, confirmPassword)
   return convertToJson(result)

@app.route('/user/sellers/<int:userId>')
def getUserSellers(userId: int):
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = SellerService()
   results = service.getUserSellers(userId)
   return convertToJson(results)

@app.route('/user/eventsAndOrders')
def getEventsAndOrders():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   excludeStart: int = None
   excludeEnd: int = None
   searchTerm: str = None
   showInactive: bool = False
   showDeleted: bool = False
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
   if request.args.get('deleted') != None:
      showDeleted = True if int(request.args.get('deleted')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd)
   return convertToJson(results)
   
@app.route("/user/setEventInactive", methods=["POST"])
def setEventInactive():
    # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   ticketSocketEventId = request.json.get("eventId", None)
   isActive = request.json.get("isActive", None)
   
   if ticketSocketEventId == None or isActive == None:
      return {"msg": "Bad Request"}, 400   
   
   disabled: bool = True if int(isActive) == 0 else False
   service = EventService()
   result = service.disableEvent(int(ticketSocketEventId), disabled)
   return convertToJson(result)

@app.route("/user/setEventDeleted", methods=["POST"])
def setEventDeleted():
    # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   ticketSocketEventId = request.json.get("eventId", None)
   isDeleted = request.json.get("isDeleted", None)
   
   if ticketSocketEventId == None or isDeleted == None:
      return {"msg": "Bad Request"}, 400   
   
   deleted: bool = True if int(isDeleted) == 1 else False
   service = EventService()
   result = service.deleteEvent(int(ticketSocketEventId), deleted)
   return convertToJson(result)

@app.route("/user/setOrderInactive", methods=["POST"])
def setOrderInactive():
    # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   ticketSocketOrderId = request.json.get("orderId", None)
   isActive = request.json.get("isActive", None)
   
   if ticketSocketOrderId == None or isActive == None:
      return {"msg": "Bad Request"}, 400   
   
   disabled: bool = True if int(isActive) == 0 else False
   service = EventService()
   result = service.disableOrder(int(ticketSocketOrderId), disabled)
   return convertToJson(result)

@app.route("/user/setOrderDeleted", methods=["POST"])
def setOrderDeleted():
    # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   ticketSocketOrderId = request.json.get("orderId", None)
   isDeleted = request.json.get("isDeleted", None)
   
   if ticketSocketOrderId == None or isDeleted == None:
      return {"msg": "Bad Request"}, 400 
   
   deleted: bool = True if int(isDeleted) == 1 else False
   service = EventService()
   result = service.deleteOrder(int(ticketSocketOrderId), deleted)
   return convertToJson(result)
   
@app.route('/public/events')
def getEvents():
   # secured by public api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('PUBLIC_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   excludeStart: int = None
   excludeEnd: int = None
   searchTerm: str = None
   showInactive: bool = False
   showDeleted: bool = False
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
   if request.args.get('deleted') != None:
      showDeleted = True if int(request.args.get('deleted')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))   
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   results = service.getEventsAndOrders(False, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd)
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
