"""
Flask API entry point
"""
import os
import sys
import json
from types import SimpleNamespace
from datetime import timedelta, timezone
from flask import Flask, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    unset_jwt_cookies,
    jwt_required,
    JWTManager,
)

from common.utility import *
from common.ticket_socket_service import *
from common.event_service import *
from common.exchange_rate_service import *
from common.update_service import *
from common.seller_service import *
from common.user_service import *
from common.environment import *

sys.path.insert(0, os.path.dirname(__file__))

# loads environment variables in debug mode
loadEnv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)
application = app


@app.after_request
def after_request(response):
    """Middleware function for authorization"""
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    response.headers.add(
        "Access-Control-Allow-Headers",
        "Content-Type,Authorization,Set-Cookie,Cookie,Cache-Control,Pragma,Expires,x-api-key",
    )
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")

    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True

    try:
        # put this line here to prevent exceptions when there is no auth header
        if request.headers.get("Authorization") is not None:
            exp_timestamp = get_jwt()["exp"]
            now = datetime.now(timezone.utc)
            target_timestamp = datetime.timestamp(now + timedelta(minutes=30))
            if target_timestamp > exp_timestamp:
                access_token = create_access_token(identity=get_jwt_identity())
                data = response.get_json()
                if isinstance(data) is dict:
                    data["access_token"] = access_token
                    response.data = json.dumps(data)
    except (RuntimeError, KeyError):
        # Case where there is not a valid JWT. Just return the original respone
        utility.logMessage("JWT not found")
    return response

def __is_admin_logged_in():
    """Check if logged in user is an admin"""
    is_admin: bool = False
    user = __get_user_from_jwt()
    if user is not None:
        is_admin = user.isAdmin
    return is_admin

def __get_user_from_jwt():
    user: User = None
    try:
        # put this line here to prevent exceptions when there is no auth header
        if request.headers.get("Authorization") is not None:
            username = get_jwt()["sub"]
            service = UserService()
            user = service.getUserByUserName(username)
    except (RuntimeError, KeyError):
        user = None
    return user

# BEGIN ADMIN ROUTES
@app.route("/admin/events/cancel", methods=["POST"])
@jwt_required()
def cancel_event():
    """
    API method to cancel an event
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)

    if event_id is None:
        return {"msg": "Bad Request"}, 400

    refund_orders_str = request.json.get("refundOrders", None)
    refund_orders: bool = True if refund_orders_str == 1 else False
    refund_service_fees: bool = False
    if refund_orders is True:
        refund_service_fees_str = request.json.get("refundServiceFees", None)
        refund_service_fees = True if refund_service_fees_str == 1 else False

    service = EventService()
    success = service.cancelEvent(int(event_id), refund_orders, refund_service_fees)
    return convertToJson(success)


@app.route("/admin/events/refund", methods=["POST"])
@jwt_required()
def refund_event():
    """
    API method to refund an event
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    event_id = request.json.get("eventId", None)

    if event_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    service = EventService()
    success = service.refundAllEventOrders(int(event_id), refund_service_fees)
    return convertToJson(success)


@app.route("/admin/events/update", methods=["POST"])
@jwt_required()
def update_event():
    """
    API method to update event
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convertToJson(request.get_json())

    event: VipEvent = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = EventService()
    success = service.updateEvent(event)
    return convertToJson(success)


@app.route("/admin/orders/refund", methods=["POST"])
@jwt_required()
def refund_order():
    """
    API method to refund order
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    order_id = request.json.get("orderId", None)

    if order_id is None:
        return {"msg": "Bad Request"}, 400

    refund_service_fees_str = request.json.get("refundServiceFees", None)
    refund_service_fees: bool = True if refund_service_fees_str == 1 else False

    mark_chargeback_str = request.json.get("markChargeback", None)
    mark_chargeback: bool = True if mark_chargeback_str == 1 else False

    service = EventService()
    success = service.refundOrder(int(order_id), refund_service_fees, mark_chargeback)
    return convertToJson(success)


@app.route("/admin/orders/update", methods=["POST"])
@jwt_required()
def update_order():
    """
    API method to update order
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convertToJson(request.get_json())

    order: VipOrder = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = EventService()
    success = service.updateOrder(order)
    return convertToJson(success)


@app.route("/admin/permissions")
@jwt_required()
def get_all_permissions():
    """
    API method to fetch all permissions
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = UserService()
    permissions = service.getAllPermissions()
    return convertToJson(permissions)

@app.route("/admin/roles")
@jwt_required()
def get_all_roles():
    """
    API method to fetch all role
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = UserService()
    roles = service.getAllRoles()
    return convertToJson(roles)

@app.route("/admin/roles/<int:roleId>")
@jwt_required()
def get_role_by_id(role_id):
    """
    API method to get role by id
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    if role_id is None or role_id <= 1:
        return {"msg": "Bad Request"}, 400

    service = UserService()
    role = service.getRoleById(role_id)
    return convertToJson(role)


@app.route("/admin/roles/delete", methods=["POST"])
@jwt_required()
def delete_roles():
    """
    API method to delete multiple roles
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convertToJson(request.get_json())

    role_ids: list[int] = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = UserService()
    success = service.deleteRoles(role_ids)
    return convertToJson(success)


@app.route("/admin/roles/update", methods=["POST"])
@jwt_required()
def update_role():
    """
    API method to update role
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convertToJson(request.get_json())

    role: Role = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = UserService()
    success = service.updateRole(role)
    return convertToJson(success)


@app.route("/admin/users")
@jwt_required()
def get_all_users():
    """
    API method to fetch all users
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    service = UserService()
    users = service.getAllUsers()
    return convertToJson(users)


@app.route("/admin/users/delete", methods=["POST"])
@jwt_required()
def delete_user():
    """
    API method to delete user
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    user_id = request.json.get("userId", None)

    if user_id is None:
        return {"msg": "Bad Request"}, 400

    service = UserService()
    success = service.deleteUser(user_id)
    return convertToJson(success)


@app.route("/admin/users/update", methods=["POST"])
@jwt_required()
def update_user():
    """
    API method to update user
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    data = convertToJson(request.get_json())

    user: User = json.loads(data, object_hook=lambda d: SimpleNamespace(**d))

    service = UserService()
    success = service.updateUser(user)
    return convertToJson(success)


# END ADMIN ROUTES


# BEGIN CRON JOB ROUTES
@app.route("/cron/updateAllEventsFromService")
def update_all_events_from_service():
    """
    API for cron to update events/orders/tickets from TicketSocket
    """
    # secured by internal api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("CRON_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = UpdateService()
    results = service.updateAllEventsFromTicketSocket()
    return convertToJson(results)


@app.route("/cron/updateAllExchangeRates")
def update_all_exchange_rates():
    """
    API for cron to update exchange rates from Stripe
    """
    # secured by internal api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("CRON_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = UpdateService()
    rates = service.updateAllExchangeRates()
    return convertToJson(rates)


# END CRON JOB ROUTES


# BEGIN DASHBOARD ROUTES
@app.route("/dashboard/getDashboardDataSecured/<int:year>")
@jwt_required()
def get_dashboard_data_secured(year: int):
    """
    API method to fetch data for dashboard
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    current_year = datetime.now().year
    if year >= current_year or year < 2022:
        year = 0

    service = EventService()
    dash_data = service.getDashboardData(year)
    return convertToJson(dash_data)


@app.route("/dashboard/getUserActivity", methods=["POST"])
@jwt_required()
def get_user_activity():
    """
    API method to fetch user activity
    """
    is_admin = __is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    start = request.json.get("start")
    end = request.json.get("end")
    user_id = request.json.get("userId")
    activity_type = request.json.get("activityType")
    filter_admins = request.json.get("filterAdmins")

    if start is None or end is None:
        return {"msg": "Bad Request"}, 400

    service = UserService()
    activities: list[UserActivity] = []
    filter_admin_val: bool = True if filter_admins is not None else False
    if user_id is not None and activity_type is not None:
        activities = service.getUserActivity(
            start, end, int(user_id), int(activity_type), filterAdmins=filter_admin_val
        )
    elif user_id is not None:
        activities = service.getUserActivity(
            start, end, int(user_id), filterAdmins=filter_admin_val
        )
    elif activity_type is not None:
        activities = service.getUserActivity(
            start, end, activityType=int(activity_type), filterAdmins=filter_admin_val
        )
    else:
        activities = service.getUserActivity(start, end, filterAdmins=filter_admin_val)
    return convertToJson(activities)


# END DASHBOARD ROUTES


# BEGIN HEALTH CHECK ROUTES
@app.route("/")
def health():
    """
    Health check API
    """
    return "All is Well\r\n"


# END HEALTH CHECK ROUTES


# BEGIN INTERNAL ROUTES
@app.route("/internal/accounts")
def get_accounts():
    """
    API method to fetch account
    """
    accounts = getAllAccounts()
    return convertToJson(accounts)


@app.route("/internal/<int:ticketSocketId>/categories")
def get_categories(ticket_socket_id: int):
    """
    API method to fetch categories
    """
    service = TicketSocketService(ticket_socket_id)
    categories = service.getCategories()
    return convertToJson(categories)


@app.route("/internal/getEventsFromService/<int:sellerId>")
def get_events_from_service(seller_id: int = None):
    """
    API method to fetch methods from TicketSocket by sellerId
    """
    service = EventService()
    start: int = None
    end: int = None
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))

    if seller_id is not None:
        results = service.retrieveTicketSocketEventsForUpdate(seller_id, start, end)
    else:
        results = None
    return convertToJson(results)


@app.route("/internal/getUpdateHistory")
@jwt_required()
def get_update_history():
    """
    API method to fetch TS refresh history
    """
    user = __get_user_from_jwt()
    if user is None or user.isAdmin is False:
        return {"msg": "Unauthorized"}, 401

    service = EventService()

    logs = service.getTicketSocketRefreshHistory()
    return convertToJson(logs)


@app.route("/internal/logUserActivity", methods=["POST"])
@jwt_required()
def log_user_activity():
    """
    API method to log user activity
    """
    success: bool = False
    user = __get_user_from_jwt()
    activity_type = request.json.get("activityType")
    activity_data = request.json.get("activityData")

    if user is not None and activity_type is not None:
        user_id = user.userId

        service = UserService()
        data: str = str(activity_data) if activity_data is not None else ""
        success = service.logUserActivity(user_id, int(activity_data), data)
    return convertToJson(success)


@app.route("/internal/mail", methods=["POST"])
def send_mail():
    """
    API to send mail via Twilio
    """
    # secured by mail api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("MAIL_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    to_email = request.json.get("toEmail", None)
    to_name = request.json.get("toName", None)
    subject = request.json.get("subject", None)
    html_content = request.json.get("htmlContent", None)
    cc_emails = request.json.get("ccEmails", None)

    if (
        to_email is None
        or to_email == ""
        or subject is None
        or subject == ""
        or html_content is None
        or html_content == ""
    ):
        return {"msg": "Bad Request"}, 200

    result = utility.sendEmail(to_email, subject, html_content, to_name, cc_emails)

    return convertToJson(result)


@app.route("/internal/refreshEventsFromService/<int:sellerId>")
@jwt_required()
def refresh_events_from_service(seller_id: int = None):
    """
    API method to refresh TS events from the admin
    """
    user = __get_user_from_jwt()
    if user is None or user.isAdmin is False:
        return {"msg": "Unauthorized"}, 401

    service = EventService()
    start: int = None
    end: int = None
    user_id: int = user.userId
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))

    if seller_id is not None:
        results = service.refreshDatabaseFromTicketSocket(seller_id, start, end, user_id)

        if results is not None and results.succeeded is True:
            # update rollup data
            year = 0
            if start is not None:
                year = datetime.fromtimestamp(start).year
                current_year = datetime.now().year
                if year >= current_year or year < 2022:
                    year = 0
            results = service.updateDailyOrderData(results, year, seller_id)
    else:
        results = None
    return convertToJson(results)


# END INTERNAL ROUTES


# BEGIN PUBLIC ROUTES
@app.route("/public/events")
def get_events():
    """
    API method for public website to fetch/search events
    """
    # secured by public api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = EventService()
    seller_id: int = None
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    ts_event_id: int = None
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("excludeStart") is not None:
        exclude_start = int(request.args.get("excludeStart"))
    if request.args.get("excludeEnd") is not None:
        exclude_end = int(request.args.get("excludeEnd"))
    if request.args.get("search") is not None:
        search_term = str(request.args.get("search"))
    if request.args.get("tsEventId") is not None:
        ts_event_id = int(request.args.get("tsEventId"))
    results = service.getEventsAndOrders(
        False,
        seller_id,
        start,
        end,
        False,
        search_term,
        ts_event_id,
        False,
        exclude_start,
        exclude_end,
        False,
        False,
    )
    return convertToJson(results)


@app.route("/public/sellers")
def get_sellers():
    """
    API method to fetch all sellers for public site
    """
    # secured by public api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("PUBLIC_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SellerService()
    results = service.getAllSellers()
    return convertToJson(results)


# END PUBLIC ROUTES


# BEGIN USER ROUTES
@app.route("/user/eventsAndOrdersSecured")
@jwt_required()
def get_events_and_orders_secured():
    """
    API method to fetch events and orders for Sellers
    """
    service = EventService()
    seller_id: int = None
    start: int = None
    end: int = None
    exclude_start: int = None
    exclude_end: int = None
    search_term: str = None
    show_inactive: bool = False
    show_deleted: bool = False
    show_hidden: bool = False
    show_cancelled: bool = False
    ts_event_id: int = None
    exclude_external: bool = False
    ignore_flags: bool = False
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("excludeStart") is not None:
        exclude_start = int(request.args.get("excludeStart"))
    if request.args.get("excludeEnd") is not None:
        exclude_end = int(request.args.get("excludeEnd"))
    if request.args.get("inactive") is not None:
        show_inactive = True if int(request.args.get("inactive")) == 1 else False
    if request.args.get("deleted") is not None:
        show_deleted = True if int(request.args.get("deleted")) == 1 else False
    if request.args.get("hidden") is not None:
        show_hidden = True if int(request.args.get("hidden")) == 1 else False
    if request.args.get("search") is not None:
        search_term = str(request.args.get("search"))
    if request.args.get("tsEventId") is not None:
        ts_event_id = int(request.args.get("tsEventId"))
    if request.args.get("excludeExternal") is not None:
        exclude_external = True if int(request.args.get("excludeExternal")) == 1 else False 
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False
    if request.args.get("cancelled") is not None:
        show_cancelled = True if int(request.args.get("cancelled")) == 1 else False
    results = service.getEventsAndOrders(
        True,
        seller_id,
        start,
        end,
        show_inactive,
        search_term,
        ts_event_id,
        show_deleted,
        exclude_start,
        exclude_end,
        exclude_external,
        show_hidden,
        ignore_flags,
        show_cancelled,
    )
    return convertToJson(results)


@app.route("/user/getUserSellerFromEventId/<int:userId>/<int:eventId>")
@jwt_required()
def get_user_seller_from_event_id(user_id: int, event_id: int):
    """
    API method to get user seller from event by event and user id's
    """
    if user_id is None or user_id == 0 or event_id is None or event_id == 0:
        return {"msg", "Bad request"}, 400
    service = UserService()
    results = service.getUserSellerByEventId(user_id, event_id)
    return convertToJson(results)


@app.route("/user/login", methods=["POST"])
def create_token():
    """
    API to log in user and create token
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    password = request.json.get("password", None)

    if username is None or password is None:
        return {"msg", "Bad request"}, 400

    service = UserService()
    login_response = service.login(username, password)

    if login_response.errorMessage is not None:
        return {"msg": login_response.errorMessage}, 401
    elif login_response.user is None or login_response.user.isAuthenticated is True:
        return {"msg": "Invalid username or password"}, 401

    access_token = create_access_token(identity=username)

    if access_token is None:
        return {"msg": "Unable to create access token"}, 500

    user: User = login_response.user
    user.token = access_token
    user.isAuthenticated = True

    return convertToJson(user)


@app.route("/user/logout", methods=["POST"])
def logout():
    """
    API method to log out user and retire token
    """
    response = jsonify({"msg": "logout successful"})
    unset_jwt_cookies(response)
    return response


@app.route("/user/ordersSecured")
@jwt_required()
def orders_secured():
    """
    API method to fetch orders for seller
    """
    service = EventService()
    seller_id: int = None
    start: int = None
    end: int = None
    show_inactive: bool = False
    show_deleted: bool = False
    show_hidden: bool = False
    show_cancelled: bool = False
    ignore_flags: bool = False
    if request.args.get("sellerId") is not None:
        seller_id = int(request.args.get("sellerId"))
    if request.args.get("start") is not None:
        start = int(request.args.get("start"))
    if request.args.get("end") is not None:
        end = int(request.args.get("end"))
    if request.args.get("inactive") is not None:
        show_inactive = True if int(request.args.get("inactive")) == 1 else False
    if request.args.get("deleted") is not None:
        show_deleted = True if int(request.args.get("deleted")) == 1 else False
    if request.args.get("hidden") is not None:
        show_hidden = True if int(request.args.get("hidden")) == 1 else False
    if request.args.get("cancelled") is not None:
        show_cancelled = True if int(request.args.get("cancelled")) == 1 else False
    if request.args.get("ignoreFlags") is not None:
        ignore_flags = True if int(request.args.get("ignoreFlags")) == 1 else False

    results = service.getOrders(
        seller_id,
        start,
        end,
        show_inactive,
        show_deleted,
        show_hidden,
        ignore_flags,
        show_cancelled,
    )
    return convertToJson(results)


@app.route("/user/profile/<int:userId>")
@jwt_required()
def get_user_profile(user_id: int):
    """
    API method to get user profile
    """
    if user_id is None or user_id <= 0:
        return {"msg": "Bad Request"}, 400
    service = UserService()
    user = service.getUserById(user_id, True)
    return convertToJson(user)


@app.route("/user/register", methods=["POST"])
def register():
    """
    API method to register new user
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    first_name = request.json.get("firstName", None)
    last_name = request.json.get("lastName", None)
    seller_id = request.json.get("sellerId", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    notes = request.json.get("notes", None)
    service = UserService()
    if (
        username is None
        or password is None
        or confirm_password is None
        or first_name is None
        or last_name is None
        or seller_id is None
    ):
        return {"msg", "Bad request"}, 400
    result = service.register(
        username, first_name, last_name, seller_id, password, confirm_password, notes
    )
    return convertToJson(result)


@app.route("/user/resetPassword", methods=["POST"])
def reset_password():
    """
    API method to reset password (not logged in)
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    code = request.json.get("code", None)
    service = UserService()
    if username is None or password is None or confirm_password is None or code is None:
        return {"msg", "Bad request"}, 400
    result = service.resetPassword(username, code, password, confirm_password)
    return convertToJson(result)


@app.route("/user/resetPasswordSecured", methods=["POST"])
@jwt_required()
def reset_password_secured():
    """
    API method to reset password (logged in)
    """
    username = request.json.get("username", None)
    password = request.json.get("password", None)
    confirm_password = request.json.get("confirmPassword", None)
    service = UserService()
    if username is None or password is None or confirm_password is None:
        return {"msg", "Bad request"}, 400
    result = service.resetPasswordSecured(username, password, confirm_password)
    return convertToJson(result)


@app.route("/user/sellers/<int:userId>")
def get_user_sellers(user_id: int):
    """
    API method to get all sellers by user_id
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    service = SellerService()
    results = service.getUserSellers(user_id)
    return convertToJson(results)


@app.route("/user/sendPasswordReset", methods=["POST"])
def send_password_reset():
    """
    API method to send password reset email with code (not logged in)
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    if username is None:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.sendPasswordResetEmail(username)
    return convertToJson(success)


@app.route("/user/setEventDeletedSecured", methods=["POST"])
@jwt_required()
def set_event_deleted_secured():
    """
    API method to mark event(s) as deleted
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_deleted = request.json.get("isDeleted", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    deleted: bool = True if int(is_deleted) == 1 else False
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    service = EventService()
    if len(event_ids) > 0:
        result = service.deleteEvents(event_ids, deleted)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setEventHiddenSecured", methods=["POST"])
@jwt_required()
def set_event_hidden_secured():
    """
    API method to mark event(s) as hidden
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_hidden = request.json.get("isHidden", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_hidden is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    hidden: bool = True if int(is_hidden) == 1 else False
    service = EventService()
    if len(event_ids) > 0:
        result = service.hideEvents(event_ids, hidden)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setEventInactiveSecured", methods=["POST"])
@jwt_required()
def set_event_inactive_secured():
    """
    API method to mark event(s) as inactive
    """
    ticket_socket_event_id = request.json.get("eventId", None)
    ticket_socket_event_id_list = request.json.get("eventIdList", None)
    is_active = request.json.get("isActive", None)

    if (
        ticket_socket_event_id is None and ticket_socket_event_id_list is None
    ) or is_active is None:
        return {"msg": "Bad Request"}, 400

    event_ids: list[int] = []
    if ticket_socket_event_id_list is not None:
        event_ids = json.loads(
            ticket_socket_event_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(event_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_event_id is not None:
        event_ids.append(int(ticket_socket_event_id))

    disabled: bool = True if int(is_active) == 0 else False
    service = EventService()
    if len(event_ids) > 0:
        result = service.disableEvents(event_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setOrderDeletedSecured", methods=["POST"])
@jwt_required()
def set_order_deleted_secured():
    """
    API method to mark order(s) as deleted
    """
    ticket_socket_order_id = request.json.get("orderId", None)
    ticket_socket_order_id_list = request.json.get("orderIdList", None)
    is_deleted = request.json.get("isDeleted", None)

    if (
        ticket_socket_order_id is None and ticket_socket_order_id_list is None
    ) or is_deleted is None:
        return {"msg": "Bad Request"}, 400

    order_ids: list[int] = []
    if ticket_socket_order_id_list is not None:
        order_ids = json.loads(
            ticket_socket_order_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(order_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_id is not None:
        order_ids.append(int(ticket_socket_order_id))

    deleted: bool = True if int(is_deleted) == 1 else False
    service = EventService()
    if len(order_ids) > 0:
        result = service.deleteOrders(order_ids, deleted)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setOrderHiddenSecured", methods=["POST"])
@jwt_required()
def set_order_hidden_secured():
    """
    API method to set order(s) as hidden
    """
    ticket_socket_order_id = request.json.get("orderId", None)
    ticket_socket_order_id_list = request.json.get("orderIdList", None)
    is_hidden = request.json.get("isHidden", None)

    if (
        ticket_socket_order_id is None and ticket_socket_order_id_list is None
    ) or is_hidden is None:
        return {"msg": "Bad Request"}, 400

    order_ids: list[int] = []
    if ticket_socket_order_id_list is not None:
        order_ids = json.loads(
            ticket_socket_order_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(order_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_id is not None:
        order_ids.append(int(ticket_socket_order_id))

    hidden: bool = True if int(is_hidden) == 1 else False
    service = EventService()
    if len(order_ids) > 0:
        result = service.hideOrders(order_ids, hidden)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setOrderInactiveSecured", methods=["POST"])
@jwt_required()
def set_order_inactive_secured():
    """
    API method to mark order(s) as inactive
    """
    ticket_socket_order_id = request.json.get("orderId", None)
    ticket_socket_order_id_list = request.json.get("orderIdList", None)
    is_active = request.json.get("isActive", None)

    if (
        ticket_socket_order_id is None and ticket_socket_order_id_list is None
    ) or is_active is None:
        return {"msg": "Bad Request"}, 400

    order_ids: list[int] = []
    if ticket_socket_order_id_list is not None:
        order_ids = json.loads(
            ticket_socket_order_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(order_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_id is not None:
        order_ids.append(int(ticket_socket_order_id))

    disabled: bool = True if int(is_active) == 0 else False
    service = EventService()
    if len(order_ids) > 0:
        result = service.disableOrders(order_ids, disabled)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/setTicketCheckinSecured", methods=["POST"])
@jwt_required()
def set_ticket_checkin_secured():
    """
    API method to mark ticket(s) as checked-in
    """
    ticket_socket_order_ticket_id = request.json.get("ticketId", None)
    ticket_socket_order_ticket_id_list = request.json.get("ticketIdList", None)
    is_checked_in = request.json.get("isCheckedIn", None)

    if (
        ticket_socket_order_ticket_id is None and ticket_socket_order_ticket_id_list is None
    ) or is_checked_in is None:
        return {"msg": "Bad Request"}, 400

    ticket_ids: list[int] = []
    if ticket_socket_order_ticket_id_list is not None:
        ticket_ids = json.loads(
            ticket_socket_order_ticket_id_list, object_hook=lambda d: SimpleNamespace(**d)
        )
        if len(ticket_ids) == 0:
            return {"msg": "Bad Request"}, 400
    elif ticket_socket_order_ticket_id is not None:
        ticket_ids.append(int(ticket_socket_order_ticket_id))

    checked_in: bool = True if int(is_checked_in) == 1 else False
    service = EventService()
    if len(ticket_ids) > 0:
        result = service.checkInTickets(ticket_ids, checked_in)
        if result is False:
            return {"msg": "Internal Server Error"}, 500
    return convertToJson(result)


@app.route("/user/validateResetCode", methods=["POST"])
def validate_reset_code():
    """
    API method to validate code sent for password reset
    """
    # secured by user api key
    sender_key = str(request.headers.get("x-api-key"))
    api_key = str(os.environ.get("USER_API_KEY"))

    if sender_key != api_key:
        return {"msg": "Unauthorized"}, 401

    username = request.json.get("username", None)
    code = request.json.get("code", None)
    if username is None or code is None:
        return {"msg", "Bad request"}, 400
    service = UserService()
    success = service.validatePasswordResetCode(str(username), int(code))
    return convertToJson(success)
# END USER ROUTES

if __name__ == "__main__":
    app.run()
