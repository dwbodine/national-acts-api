import json
import re

from . import db

class GenericJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        objDict=obj.__dict__
        typeDict={"__type__":type(obj).__name__}
        return {**objDict,**typeDict}
    
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

def queueEmail(subject, html, toAddress, toName, ccEmails):
    sql = "INSERT INTO MailServiceQueue (ToAddress, ToName, Subject, Message, CcEmails) VALUES (%(toAddress)s, %(toName)s, %(subject)s, %(html)s, %(ccEmails)s)"

    data = {
        'to_address': toAddress,
        'to_name': toName,
        'subject': subject,
        'html': html,
        'cc_emails': ccEmails
    }

    result = db.insert(sql, data)

    return (result > 0)