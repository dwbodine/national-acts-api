"""
Flask API entry point
"""

import os
import sys
import json
from datetime import timedelta, timezone, datetime
import traceback

from flask import Flask, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    JWTManager,
    jwt_required,
)

from api.admin_api import admin_api
from api.cron_api import cron_api
from api.dashboard_api import dashboard_api
from api.event_api import event_api
from api.internal_api import internal_api
from api.public_api import public_api
from api.user_api import user_api

from common.common_api import is_admin_logged_in
from common.utility import log_message, convert_to_json
from common.environment import load_env

sys.path.insert(0, os.path.dirname(__file__))

# loads environment variables in debug mode
load_env()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)
jwt = JWTManager(app)
application = app

app.register_blueprint(admin_api)
app.register_blueprint(cron_api)
app.register_blueprint(dashboard_api)
app.register_blueprint(event_api)
app.register_blueprint(internal_api)
app.register_blueprint(public_api)
app.register_blueprint(user_api)


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
                if isinstance(data, dict):
                    data["access_token"] = access_token
                    response.data = json.dumps(data)
    except (RuntimeError, KeyError):
        # Case where there is not a valid JWT. Just return the original respone
        log_message("JWT not found")
    except Exception as error:  # pylint: disable=broad-exception-caught
        error_message: str = str(error) + "\n" + traceback.format_exc()
        log_message(error_message)
    return response


@app.route("/")
def health():
    """
    Health check API
    """
    return "All is Well\r\n"


@app.route("/log")
@jwt_required()
def view_log():
    """
    View log for admins only
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    log_data: str = None
    with open("passenger.log", "r", encoding="utf8") as f:
        log_data = f.read()

    return convert_to_json(log_data)


@app.route("/cron_log")
@jwt_required()
def view_cron_log():
    """
    View cron log for admins only
    """
    is_admin = is_admin_logged_in()
    if is_admin is False:
        return {"msg": "Unauthorized"}, 401

    log_data: str = None
    with open("cron.log", "r", encoding="utf8") as f:
        log_data = f.read()

    return convert_to_json(log_data)


if __name__ == "__main__":
    app.run()
