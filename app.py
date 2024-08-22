import os
import sys
from datetime import timedelta, timezone
from flask import Flask, request, jsonify
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, verify_jwt_in_request, unset_jwt_cookies, jwt_required, JWTManager
import json
from types import SimpleNamespace

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
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
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
      utility.logMessage('JWT not found')
   return response

def __isAdminLoggedIn():
   isAdmin: bool = False
   user = __getUserFromJwt()
   if user != None:
      isAdmin = user.isAdmin
   return isAdmin

def __getUserFromJwt():
   user: User = None
   try:
      # put this line here to prevent exceptions when there is no auth header
      if request.headers.get("Authorization") != None:
         username = get_jwt()["sub"]
         service = UserService()
         user = service.getUserByUserName(username)
   except:
      user = None
   return user

@app.route('/')
def health():
   return 'All is Well\r\n'

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
   
   if access_token == None:
      return {"msg": "Unable to create access token"}, 500
   
   user: User = loginResponse.user
   user.token = access_token
   user.isAuthenticated = True
   
   return convertToJson(user)

@app.route("/user/logout", methods=["POST"])
def logout():
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response

@app.route('/user/profile/<int:userId>')
@jwt_required()
def getUserProfile(userId: int):
   if userId == None or userId <= 0:
      return {"msg": "Bad Request"}, 400
   service = UserService()
   user = service.getUserById(userId, True)
   return convertToJson(user)

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

@app.route("/user/resetPasswordSecured", methods=["POST"])
@jwt_required()
def resetPasswordSecured():
   username = request.json.get("username", None)
   password = request.json.get("password", None)
   confirmPassword = request.json.get("confirmPassword", None)
   service = UserService()
   if username == None or password == None or confirmPassword == None:
      return {"msg", "Bad request"}, 400
   result = service.resetPasswordSecured(username, password, confirmPassword)
   return convertToJson(result)

@app.route("/user/register", methods=["POST"])
def register():
   # secured by user api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('USER_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   username = request.json.get("username", None)
   firstName = request.json.get("firstName", None)
   lastName = request.json.get("lastName", None)
   sellerId = request.json.get("sellerId", None)
   password = request.json.get("password", None)
   confirmPassword = request.json.get("confirmPassword", None)
   notes = request.json.get("notes", None)
   service = UserService()
   if username == None or password == None or confirmPassword == None or firstName == None or lastName == None or sellerId == None:
      return {"msg", "Bad request"}, 400
   result = service.register(username, firstName, lastName, sellerId, password, confirmPassword, notes)
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
   excludeExternal: bool = False
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
      excludeExternal = True
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd, excludeExternal)
   return convertToJson(results)

@app.route('/user/eventsAndOrdersSecured')
@jwt_required()
def getEventsAndOrdersSecured():
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
   excludeExternal: bool = False
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
   if request.args.get('excludeExternal') != None:
      excludeExternal = True if int(request.args.get('excludeExternal')) == 1 else False
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd, excludeExternal)
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

@app.route("/user/setEventInactiveSecured", methods=["POST"])
@jwt_required()
def setEventInactiveSecured():
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

@app.route("/user/setEventDeletedSecured", methods=["POST"])
@jwt_required()
def setEventDeletedSecured():
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

@app.route("/user/setOrderInactiveSecured", methods=["POST"])
@jwt_required()
def setOrderInactiveSecured():
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

@app.route("/user/setOrderDeletedSecured", methods=["POST"])
@jwt_required()
def setOrderDeletedSecured():
   ticketSocketOrderId = request.json.get("orderId", None)
   isDeleted = request.json.get("isDeleted", None)
   
   if ticketSocketOrderId == None or isDeleted == None:
      return {"msg": "Bad Request"}, 400 
   
   deleted: bool = True if int(isDeleted) == 1 else False
   service = EventService()
   result = service.deleteOrder(int(ticketSocketOrderId), deleted)
   return convertToJson(result)

@app.route("/user/setTicketCheckinSecured", methods=["POST"])
@jwt_required()
def setTicketCheckinSecured():
   ticketSocketOrderTicketId = request.json.get("ticketId", None)
   isCheckedIn = request.json.get("isCheckedIn", None)
   
   if ticketSocketOrderTicketId == None or isCheckedIn == None:
      return {"msg": "Bad Request"}, 400   
   
   checkedIn: bool = True if int(isCheckedIn) == 1 else False
   service = EventService()
   result = service.checkInTicket(ticketSocketOrderTicketId, checkedIn)
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

@app.route('/public/sellers')
def getSellers():
   # secured by public api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('PUBLIC_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = SellerService()
   results = service.getAllSellers()
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
   # secured by internal api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('INTERNAL_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = UpdateService()
   results = service.updateAllEventsFromTicketSocket()
   return convertToJson(results)

@app.route('/internal/updateAllExchangeRates')
def updateAllExchangeRates():
   # secured by internal api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('INTERNAL_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
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

@app.route('/external/checkin')
def checkin():
   utility.logMessage('Webhook activated - GET')
   args = utility.convertToJson(request.args)
   utility.logMessage(args)
   return convertToJson(True)

@app.route('/external/checkin', methods=["POST"])
def checkinPost():
   utility.logMessage('Webhook activated - POST')
   body = utility.convertToJson(request.json)
   utility.logMessage(body)
   return convertToJson(True)

@app.route('/admin/users')
@jwt_required()
def getAllUsers():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = UserService()
   users = service.getAllUsers()
   return convertToJson(users)   

@app.route('/admin/roles')
@jwt_required()
def getAllRoles():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = UserService()
   roles = service.getAllRoles()
   return convertToJson(roles) 

@app.route('/admin/roles/<int:roleId>')
@jwt_required()
def getRoleById(roleId):
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   if roleId == None or roleId <= 1:
      return {"msg": "Bad Request"}, 400 
   
   service = UserService()
   role = service.getRoleById(roleId)
   return convertToJson(role) 

@app.route('/admin/permissions')
@jwt_required()
def getAllPermissions():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = UserService()
   permissions = service.getAllPermissions()
   return convertToJson(permissions) 

@app.route('/admin/updateRole', methods=["POST"])
@jwt_required()
def updateRole():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   data = convertToJson(request.get_json())
   
   role: Role = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
   
   service = UserService()
   success = service.updateRole(role)
   return convertToJson(success) 

@app.route('/admin/deleteRoles', methods=["POST"])
@jwt_required()
def deleteRoles():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   data = convertToJson(request.get_json())
   
   roleIds: list[int] = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
   
   service = UserService()
   success = service.deleteRoles(roleIds)
   return convertToJson(success) 

@app.route('/admin/updateUser', methods=["POST"])
@jwt_required()
def updateUser():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   data = convertToJson(request.get_json())
   
   user: User = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
   
   service = UserService()
   success = service.updateUser(user)
   return convertToJson(success) 

@app.route('/internal/logUserActivity', methods=["POST"])
@jwt_required()
def logUserActivity():
   success: bool = False
   user = __getUserFromJwt()
   activityType = request.json.get("activityType")
   activityData = request.json.get("activityData")
   
   if user != None and activityType != None:
      userId = user.userId     
      
      service = UserService()
      data: str = str(activityData) if activityData != None else ''
      success = service.logUserActivity(userId, int(activityType), data)
   return convertToJson(success)

@app.route('/dashboard/getUserActivity', methods=["POST"])
@jwt_required()
def getUserActivity():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   start = request.json.get("start")
   end = request.json.get("end")
   userId = request.json.get("userId")
   activityType = request.json.get("activityType")
   filterAdmins = request.json.get("filterAdmins")
   
   if start == None or end == None:
      return {"msg": "Bad Request"}, 400
   
   service = UserService()
   activities: list[UserActivity] = []
   filterAdminVal: bool = True if filterAdmins != None else False
   if userId != None and activityType != None:
      activities = service.getUserActivity(start, end, int(userId), int(activityType), filterAdmins=filterAdminVal)
   elif userId != None:
      activities = service.getUserActivity(start, end, int(userId), filterAdmins=filterAdminVal)
   elif activityType != None:
      activities = service.getUserActivity(start, end, activityType=int(activityType), filterAdmins=filterAdminVal)
   else:
      activities = service.getUserActivity(start, end, filterAdmins=filterAdminVal)
   return convertToJson(activities)
      
      

if __name__ == "__main__":
    app.run()
