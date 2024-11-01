"""
Utilites for Python app
"""
import json
import re
import os
from datetime import datetime
import traceback
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To

class GenericJsonEncoder(json.JSONEncoder):
    """
    JSON encoding utility
    """
    def default(self, o):
        obj_dict=o.__dict__
        type_dict={"__type__":type(o).__name__}
        return {**obj_dict,**type_dict}

class SendEmailResult:
    """
    Class for sending email
    """
    def __init__(self, success: bool, error: str = None):
        self.success = success
        self.error = error

def send_email(to_email_address: str, subject: str, html_content: str, to_name: str = None, cc_emails: list[str] = None):
    """
    Utility to send email through Twilio
    """
    from_email = From('info@national-acts.com', 'National Acts VIP')

    if to_name is not None and to_name != "":
        to_email = To(to_email_address, to_name)    
    else:
        to_email = to_email_address    

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content)

    if cc_emails is not None:
        for email in cc_emails:
            message.add_cc(email)

    result: SendEmailResult = None
    try:
        send_grid_key = os.environ.get('SENDGRID_API_KEY')
        sg = SendGridAPIClient(send_grid_key)
        sg.send(message)
        result = SendEmailResult(True, None)
    except (SystemError, RuntimeError, TimeoutError) as e:
        result = SendEmailResult(False, str(e) + "\n" + traceback.format_exc())

    return result

def convert_to_json(obj: any):
    """
    Convert any object to JSON
    """
    return json.dumps(obj, indent=4, ensure_ascii=False, cls=GenericJsonEncoder)

def format_phone(raw: str):
    """
    Formatting for USA phone numbers
    """
    parsed = re.sub('[^0-9]', '', raw)
    phone = parsed
    if len(parsed) >= 10:
        if len(parsed) > 10 and parsed[0:1] == '1':
            parsed = parsed[1:11]
        else:
            parsed = parsed[0:10]
        phone = "(" + parsed[0:3] + ") " + parsed[3:6] + "-" + parsed[6:]
    elif len(parsed) >= 7:
        phone = parsed[0:3] + "-" + parsed[3:7]

    return phone

def fix_magic_quotes(raw: str):
    """
    Replace unicode magic quotes with ASCII equivalents
    """
    raw = raw.replace(u'\u201c', '"')
    raw = raw.replace(u'\u201d', '"')
    raw = raw.replace(u"\u2018", "'")
    raw = raw.replace(u"\u2019", "'")
    return raw

def add_months(current_date: datetime, months_to_add: int):
    """
    Add a number of months to a date
    """
    new_date = datetime(current_date.year + (current_date.month + months_to_add - 1) // 12,
                        (current_date.month + months_to_add - 1) % 12 + 1,
                        current_date.day)
    return new_date

def validate_email_address(email: str):
    """
    Validate email address
    """
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    return re.fullmatch(regex, email)

def log_message(msg: str):
    """
    Write message to the log
    """
    date_str = datetime.now().isoformat()
    print('[' + date_str + '] ' + msg)
