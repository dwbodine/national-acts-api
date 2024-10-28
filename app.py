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

# BEGIN ADMIN ROUTES
@app.route('/admin/events/cancel', methods=["POST"])
@jwt_required()
def cancelEvent():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   eventId = request.json.get("eventId", None)
   
   if eventId == None:
      return {"msg": "Bad Request"}, 400
   
   refundOrdersStr = request.json.get("refundOrders", None)
   refundOrders: bool = True if refundOrdersStr == 1 else False
   refundServiceFees: bool = False
   if refundOrders == True:
      refundServiceFeesStr = request.json.get("refundServiceFees", None)
      refundServiceFees = True if refundServiceFeesStr == 1 else False   
   
   service = EventService()
   success = service.cancelEvent(int(eventId), refundOrders, refundServiceFees)
   return convertToJson(success) 

@app.route('/admin/events/refund', methods=["POST"])
@jwt_required()
def refundEvent():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   eventId = request.json.get("eventId", None)
   
   if eventId == None:
      return {"msg": "Bad Request"}, 400
   
   refundServiceFeesStr = request.json.get("refundServiceFees", None)
   refundServiceFees: bool = True if refundServiceFeesStr == 1 else False   
   
   service = EventService()
   success = service.refundAllEventOrders(int(eventId), True, refundServiceFees)
   return convertToJson(success) 

@app.route('/admin/events/update', methods=["POST"])
@jwt_required()
def updateEvent():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   data = convertToJson(request.get_json())
   
   event: VipEvent = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
   
   service = EventService()
   success = service.updateEvent(event)
   return convertToJson(success) 

@app.route('/admin/orders/refund', methods=["POST"])
@jwt_required()
def refundOrder():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   orderId = request.json.get("orderId", None)
   
   if orderId == None:
      return {"msg": "Bad Request"}, 400
   
   refundServiceFeesStr = request.json.get("refundServiceFees", None)
   refundServiceFees: bool = True if refundServiceFeesStr == 1 else False   
   
   service = EventService()
   success = service.refundOrder(int(orderId), refundServiceFees)
   return convertToJson(success) 

@app.route('/admin/orders/update', methods=["POST"])
@jwt_required()
def updateOrder():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   data = convertToJson(request.get_json())
   
   order: VipOrder = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))
   
   service = EventService()
   success = service.updateOrder(order)
   return convertToJson(success) 

@app.route('/admin/permissions')
@jwt_required()
def getAllPermissions():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = UserService()
   permissions = service.getAllPermissions()
   return convertToJson(permissions) 

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

@app.route('/admin/roles/delete', methods=["POST"])
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

@app.route('/admin/roles/update', methods=["POST"])
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

@app.route('/admin/users')
@jwt_required()
def getAllUsers():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = UserService()
   users = service.getAllUsers()
   return convertToJson(users)  

@app.route('/admin/users/delete', methods=["POST"])
@jwt_required()
def deleteUser():
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   userId = request.json.get("userId", None)
   
   if userId == None:
      return {"msg": "Bad Request"}, 400
   
   service = UserService()
   success = service.deleteUser(userId)
   return convertToJson(success) 

@app.route('/admin/users/update', methods=["POST"])
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
# END ADMIN ROUTES

# BEGIN CRON JOB ROUTES
@app.route('/cron/updateAllEventsFromService')
def updateAllEventsFromService():
   # secured by internal api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('CRON_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = UpdateService()
   results = service.updateAllEventsFromTicketSocket()
   return convertToJson(results)

@app.route('/cron/updateAllExchangeRates')
def updateAllExchangeRates():
   # secured by internal api key
   senderKey = str(request.headers.get('x-api-key'))
   apiKey = str(os.environ.get('CRON_API_KEY'))
   
   if (senderKey != apiKey):
      return {"msg": "Unauthorized"}, 401
   
   service = UpdateService()
   rates = service.updateAllExchangeRates()
   return convertToJson(rates)
# END CRON JOB ROUTES

# BEGIN DASHBOARD ROUTES
@app.route('/dashboard/getDashboardDataSecured/<int:year>')
@jwt_required()
def getDashboardDataSecured(year: int):
   isAdmin = __isAdminLoggedIn()
   if isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   currentYear = datetime.now().year
   if year >= currentYear or year < 2022:
      year = 0
   
   service = EventService()
   dashData = service.getDashboardData(year)
   return convertToJson(dashData) 

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
# END DASHBOARD ROUTES

# BEGIN EXTERNAL ROUTES
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
# END EXTERNAL ROUTES

# BEGIN HEALTH CHECK ROUTES
@app.route('/')
def health():
   return 'All is Well\r\n'
# END HEALTH CHECK ROUTES

# BEGIN INTERNAL ROUTES
@app.route('/internal/accounts')
def getAccounts():
   accounts = getAllAccounts()
   return convertToJson(accounts)

@app.route('/internal/<int:ticketSocketId>/categories')
def getCategories(ticketSocketId):
   service = TicketSocketService(ticketSocketId)
   categories = service.getCategories()
   return convertToJson(categories)

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

@app.route('/internal/getUpdateHistory')
@jwt_required()
def getUpdateHistory():
   user = __getUserFromJwt()
   if user == None or user.isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = EventService()

   logs = service.getTicketSocketRefreshHistory()
   return convertToJson(logs)

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

@app.route('/internal/refreshEventsFromService/<int:sellerId>')
@jwt_required()
def refreshEventsFromService(sellerId: int = None):
   user = __getUserFromJwt()
   if user == None or user.isAdmin == False:
      return {"msg": "Unauthorized"}, 401
   
   service = EventService()
   start: int = None
   end: int = None
   userId: int = user.userId
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   
   if sellerId != None:
      results = service.refreshDatabaseFromTicketSocket(sellerId, start, end, userId)
      
      if results != None and results.succeeded == True:
         # update rollup data
         year = 0
         if start != None:
            year = datetime.fromtimestamp(start).year
            currentYear = datetime.now().year
            if year >= currentYear or year < 2022:
               year = 0         
         results = service.updateDailyOrderData(results, year, sellerId)
   else:
      results = None
   return convertToJson(results)
# END INTERNAL ROUTES


# BEGIN PUBLIC ROUTES   
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
   showHidden: bool = False
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
   if request.args.get('hidden') != None:
      showHidden = True if int(request.args.get('hidden')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))   
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   results = service.getEventsAndOrders(False, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd, showHidden, False)
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
# END PUBLIC ROUTES

# BEGIN USER ROUTES
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
   showHidden: bool = False
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
   if request.args.get('hidden') != None:
      showHidden = True if int(request.args.get('hidden')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
      excludeExternal = True
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd, excludeExternal, showHidden, False)
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
   showHidden: bool = False
   tsEventId: int = None
   excludeExternal: bool = False
   ignoreFlags: bool = False
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
   if request.args.get('hidden') != None:
      showHidden = True if int(request.args.get('hidden')) == 1 else False
   if request.args.get('search') != None:
      searchTerm = str(request.args.get('search'))
   if request.args.get('tsEventId') != None:
      tsEventId = int(request.args.get('tsEventId'))
   if request.args.get('excludeExternal') != None:
      excludeExternal = True if int(request.args.get('excludeExternal')) == 1 else False
   if request.args.get('ignoreFlags') != None:
      ignoreFlags = True if int(request.args.get('ignoreFlags')) == 1 else False
   results = service.getEventsAndOrders(True, sellerId, start, end, showInactive, searchTerm, tsEventId, showDeleted, excludeStart, excludeEnd, excludeExternal, showHidden, ignoreFlags)
   return convertToJson(results)

@app.route('/user/getUserSellerFromEventId/<int:userId>/<int:eventId>')
@jwt_required()
def getUserSellerFromEventId(userId: int, eventId: int):   
   if userId == None or userId == 0 or eventId == None or eventId == 0:
      return {"msg", "Bad request"}, 400
   service = UserService()
   results = service.getUserSellerByEventId(userId, eventId)
   return convertToJson(results)

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
 
@app.route('/user/ordersSecured')
@jwt_required()
def ordersSecured():
   service = EventService()
   sellerId: int = None
   start: int = None
   end: int = None
   showInactive: bool = False
   showDeleted: bool = False
   showHidden: bool = False
   ignoreFlags: bool = False
   getYearToDateTotals: bool = False
   if request.args.get('sellerId') != None:
      sellerId = int(request.args.get('sellerId'))
   if request.args.get('start') != None:
      start = int(request.args.get('start'))
   if request.args.get('end') != None:
      end = int(request.args.get('end'))
   if request.args.get('inactive') != None:
      showInactive = True if int(request.args.get('inactive')) == 1 else False
   if request.args.get('deleted') != None:
      showDeleted = True if int(request.args.get('deleted')) == 1 else False
   if request.args.get('hidden') != None:
      showHidden = True if int(request.args.get('hidden')) == 1 else False
   if request.args.get('ignoreFlags') != None:
      ignoreFlags = True if int(request.args.get('ignoreFlags')) == 1 else False
   if request.args.get('getYearToDateTotals') != None:
      getYearToDateTotals = True if int(request.args.get('getYearToDateTotals')) == 1 else False
   results = service.getOrders(sellerId, start, end, showInactive, showDeleted, showHidden, ignoreFlags, getYearToDateTotals)
   return convertToJson(results)

@app.route('/user/profile/<int:userId>')
@jwt_required()
def getUserProfile(userId: int):
   if userId == None or userId <= 0:
      return {"msg": "Bad Request"}, 400
   service = UserService()
   user = service.getUserById(userId, True)
   return convertToJson(user)

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

@app.route("/user/setEventDeletedSecured", methods=["POST"])
@jwt_required()
def setEventDeletedSecured():
   ticketSocketEventId = request.json.get("eventId", None)
   ticketSocketEventIdList = request.json.get("eventIdList", None)
   isDeleted = request.json.get("isDeleted", None)
   
   if (ticketSocketEventId == None and ticketSocketEventIdList == None) or isDeleted == None:
      return {"msg": "Bad Request"}, 400 
   
   eventIds: list[int] = []
   deleted: bool = True if int(isDeleted) == 1 else False
   if ticketSocketEventIdList != None:
      eventIds = json.loads(ticketSocketEventIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(eventIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketEventId != None:
      eventIds.append(int(ticketSocketEventId))
   
   service = EventService()
   if len(eventIds) > 0:
      result = service.deleteEvents(eventIds, deleted)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setEventHiddenSecured", methods=["POST"])
@jwt_required()
def setEventHiddenSecured():
   ticketSocketEventId = request.json.get("eventId", None)
   ticketSocketEventIdList = request.json.get("eventIdList", None)
   isHidden = request.json.get("isHidden", None)
   
   if (ticketSocketEventId == None and ticketSocketEventIdList == None) or isHidden == None:
      return {"msg": "Bad Request"}, 400 
   
   eventIds: list[int] = []
   if ticketSocketEventIdList != None:
      eventIds = json.loads(ticketSocketEventIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(eventIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketEventId != None:
      eventIds.append(int(ticketSocketEventId))
   
   hidden: bool = True if int(isHidden) == 1 else False
   service = EventService()
   if len(eventIds) > 0:
      result = service.hideEvents(eventIds, hidden)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setEventInactiveSecured", methods=["POST"])
@jwt_required()
def setEventInactiveSecured():
   ticketSocketEventId = request.json.get("eventId", None)
   ticketSocketEventIdList = request.json.get("eventIdList", None)
   isActive = request.json.get("isActive", None)
   
   if (ticketSocketEventId == None and ticketSocketEventIdList == None) or isActive == None:
      return {"msg": "Bad Request"}, 400   
   
   eventIds: list[int] = []
   if ticketSocketEventIdList != None:
      eventIds = json.loads(ticketSocketEventIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(eventIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketEventId != None:
      eventIds.append(int(ticketSocketEventId))
   
   disabled: bool = True if int(isActive) == 0 else False
   service = EventService()
   if len(eventIds) > 0:
      result = service.disableEvents(eventIds, disabled)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setOrderDeletedSecured", methods=["POST"])
@jwt_required()
def setOrderDeletedSecured():
   ticketSocketOrderId = request.json.get("orderId", None)
   ticketSocketOrderIdList = request.json.get("orderIdList", None)
   isDeleted = request.json.get("isDeleted", None)
   
   if (ticketSocketOrderId == None and ticketSocketOrderIdList == None) or isDeleted == None:
      return {"msg": "Bad Request"}, 400 
   
   orderIds: list[int] = []
   if ticketSocketOrderIdList != None:
      orderIds = json.loads(ticketSocketOrderIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(orderIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketOrderId != None:
      orderIds.append(int(ticketSocketOrderId))
   
   deleted: bool = True if int(isDeleted) == 1 else False
   service = EventService()
   if len(orderIds) > 0:
      result = service.deleteOrders(orderIds, deleted)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setOrderHiddenSecured", methods=["POST"])
@jwt_required()
def setOrderHiddenSecured():
   ticketSocketOrderId = request.json.get("orderId", None)
   ticketSocketOrderIdList = request.json.get("orderIdList", None)
   isHidden = request.json.get("isHidden", None)
   
   if (ticketSocketOrderId == None and ticketSocketOrderIdList == None) or isHidden == None:
      return {"msg": "Bad Request"}, 400 
   
   orderIds: list[int] = []
   if ticketSocketOrderIdList != None:
      orderIds = json.loads(ticketSocketOrderIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(orderIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketOrderId != None:
      orderIds.append(int(ticketSocketOrderId))    
   
   hidden: bool = True if int(isHidden) == 1 else False
   service = EventService()
   if len(orderIds) > 0:
      result = service.hideOrders(orderIds, hidden)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setOrderInactiveSecured", methods=["POST"])
@jwt_required()
def setOrderInactiveSecured():
   ticketSocketOrderId = request.json.get("orderId", None)
   ticketSocketOrderIdList = request.json.get("orderIdList", None)
   isActive = request.json.get("isActive", None)
   
   if (ticketSocketOrderId == None and ticketSocketOrderIdList == None) or isActive == None:
      return {"msg": "Bad Request"}, 400   
   
   orderIds: list[int] = []
   if ticketSocketOrderIdList != None:
      orderIds = json.loads(ticketSocketOrderIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(orderIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketOrderId != None:
      orderIds.append(int(ticketSocketOrderId))
   
   disabled: bool = True if int(isActive) == 0 else False
   service = EventService()
   if len(orderIds) > 0:
      result = service.disableOrders(orderIds, disabled)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)

@app.route("/user/setTicketCheckinSecured", methods=["POST"])
@jwt_required()
def setTicketCheckinSecured():
   ticketSocketOrderTicketId = request.json.get("ticketId", None)
   ticketSocketOrderTicketIdList = request.json.get("ticketIdList", None)
   isCheckedIn = request.json.get("isCheckedIn", None)
   
   if (ticketSocketOrderTicketId == None and ticketSocketOrderTicketIdList == None) or isCheckedIn == None:
      return {"msg": "Bad Request"}, 400   
   
   ticketIds: list[int] = []
   if ticketSocketOrderTicketIdList != None:
      ticketIds = json.loads(ticketSocketOrderTicketIdList, object_hook=lambda d: SimpleNamespace(**d))
      if len(ticketIds) == 0:
         return {"msg": "Bad Request"}, 400
   elif ticketSocketOrderTicketId != None:
      ticketIds.append(int(ticketSocketOrderTicketId))
   
   checkedIn: bool = True if int(isCheckedIn) == 1 else False
   service = EventService()
   if len(ticketIds) > 0:
      result = service.checkInTickets(ticketIds, checkedIn)      
      if result == False:
         return {"msg": "Internal Server Error"}, 500
   return convertToJson(result)
   
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
# END USER ROUTES

if __name__ == "__main__":
    app.run()
