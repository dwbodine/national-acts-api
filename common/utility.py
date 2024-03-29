import json
import re
import os
from datetime import datetime
from . import db
import traceback
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To

class GenericJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        objDict=obj.__dict__
        typeDict={"__type__":type(obj).__name__}
        return {**objDict,**typeDict}
    
class SendEmailResult:
    def __init__(self, success: bool, error: str = None):
        self.success = success
        self.error = error
    
def sendEmail(toEmailAddress: str, subject: str, htmlContent: str, toName: str = None, ccEmails: list[str] = None):
    fromEmail = From('info@national-acts.com', 'National Acts VIP')
    
    if toName != None and toName != "":
        toEmail = To(toEmailAddress, toName)    
    else:
        toEmail = toEmailAddress    
    
    message = Mail(
        from_email=fromEmail,
        to_emails=toEmail,
        subject=subject,
        html_content=htmlContent)
    
    if ccEmails != None:
        for email in ccEmails:
            message.add_cc(email)
   
    result: SendEmailResult = None
    try:
        sendGridKey = os.environ.get('SENDGRID_API_KEY')
        sg = SendGridAPIClient(sendGridKey)
        response = sg.send(message)
        result = SendEmailResult(True, None)
    except Exception as e:
        result = SendEmailResult(False, str(e) + "\n" + traceback.format_exc())
        
    return result
    
def convertToJson(obj: any):
    return json.dumps(obj, indent=4, ensure_ascii=False, cls=GenericJsonEncoder)

def formatPhone(raw: str):
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

def fixMagicQuotes(raw: str):
    raw = raw.replace(u'\u201c', '"')
    raw = raw.replace(u'\u201d', '"')
    raw = raw.replace(u"\u2018", "'")
    raw = raw.replace(u"\u2019", "'")
    return raw

def add_months(current_date, months_to_add):
    new_date = datetime(current_date.year + (current_date.month + months_to_add - 1) // 12,
                        (current_date.month + months_to_add - 1) % 12 + 1,
                        current_date.day)
    return new_date

def validateEmailAddress(email: str):
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    return re.fullmatch(regex, email)

def logMessage(msg: str):
    dateStr = datetime.now().isoformat()
    print('[' + dateStr + '] ' + msg)