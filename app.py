"""
Flask API entry point
"""

import os
from os.path import join, dirname
import sys
import json
from datetime import timedelta, timezone, datetime
import traceback
import logging
import io
from dotenv import load_dotenv
from flask import Flask, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    JWTManager,
)
from mariadb import Connection

from api.admin_api import admin_api
from api.cron_api import cron_api
from api.dashboard_api import dashboard_api
from api.event_api import event_api
from api.internal_api import internal_api
from api.public_api import public_api
from api.user_api import user_api
from api.report_api import report_api
from api.messaging_api import messaging_api
from api.ticket_orders_api import ticket_orders_api
from common.db import db_get_connection

current_path = os.path.dirname(__file__)
sys.path.insert(0, current_path)

# loads environment variables in debug mode
if os.environ.get("FLASK_ENV") == "production":
    load_dotenv(override=True)
else:
    dotenv_path = join(dirname(__file__), ".env.development")
    load_dotenv(dotenv_path, override=True)

log_stream = io.StringIO()

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)

memory_handler = logging.StreamHandler(log_stream)
memory_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stdout_handler.setFormatter(formatter)
memory_handler.setFormatter(formatter)

if root_logger.hasHandlers():
    root_logger.handlers.clear()

root_logger.addHandler(stdout_handler)
root_logger.addHandler(memory_handler)

gunicorn_error_logger = logging.getLogger("gunicorn.error")
flask_logger = logging.getLogger("flask.app")
flask_logger.handlers = gunicorn_error_logger.handlers
flask_logger.setLevel(logging.INFO)

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
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
app.register_blueprint(report_api)
app.register_blueprint(messaging_api)
app.register_blueprint(ticket_orders_api)


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
        root_logger.info("JWT not found")
    except Exception as error:  # pylint: disable=broad-exception-caught
        error_message: str = str(error) + "\n" + traceback.format_exc()
        root_logger.error(error_message)
    return response


@app.route("/")
def health():
    """
    Health check API
    """
    conn: Connection = None
    message: str = None
    header: str = "<h1>Health Check</h1><p>"
    try:
        conn = db_get_connection()
    except Exception as error:  # pylint: disable=broad-exception-caught
        message = str(error) + "\n" + traceback.format_exc()
        conn = None

    if message is not None:
        return f"""{header} Server is up
             but database connection failed with message:<br /><br />
             {message.replace('\r', '').replace('\n', '<br />')}</p>\r\n"""
    elif conn is not None:
        if conn.open:
            conn.close()
            return f"{header}Server is up and database available</p>\r\n"
        else:
            return f"{header}Server is up but database connection failed</p>\r\n"
    else:
        return f"{header}Server is up but database not available</p>\r\n"


if __name__ == "__main__":
    app.run()
