import time

from .conn import SkypeConnection
from .event import SkypeEvent, SkypePresenceEvent, SkypeMessageEvent

class Skype(object):
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.conn = SkypeConnection(user, pwd, tokenFile)
        self.user = self.getUser()
        self.contacts = self.getContacts()
    def getUser(self):
        json = self.conn("GET", "https://api.skype.com/users/self/displayname", auth=SkypeConnection.Auth.Skype).json()
        return SkypeUser(id=json.get("username"), type="skype", name={
            "first": json.get("firstname"),
            "last": json.get("lastname"),
            "display": json.get("displayname")
        })
    def getContacts(self):
        contacts = []
        for json in self.conn("GET", "https://contacts.skype.com/contacts/v1/users/" + self.user.id + "/contacts", auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            loc = None
            if json.get("locations"):
                loc = json["locations"][0]
                loc["country"] = loc["country"].upper()
            contacts.append(SkypeUser(id=json.get("id"), type=json.get("type"), name={
                "first": json["name"].get("first"),
                "last": json["name"].get("surname"),
                "display": json.get("display_name")
            }, location=loc, phones=json.get("phones")))
        return sorted(contacts, key=(lambda user: user.id.split(":")[-1]))
    @SkypeConnection.resubscribeOn(404)
    def getEvents(self):
        events = []
        for json in self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.Auth.Reg).json().get("eventMessages", []):
            resType = json.get("resourceType")
            if resType == "UserPresence":
                ev = SkypePresenceEvent(json)
            elif resType == "NewMessage":
                ev = SkypeMessageEvent(json)
            else:
                ev = SkypeEvent(json)
            events.append(ev)
        return events
    def sendMsg(self, conv, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = self.conn("POST", self.conn.msgsHost + "/conversations/" + conv + "/messages", auth=SkypeConnection.Auth.Reg, json={
            "clientmessageid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        return msgId
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.user.id)

class SkypeUser(object):
    def __init__(self, id, type="skype", name={}, location=None, phones=[]):
        self.id = id
        self.type = type
        self.name = name
        self.location = location
        self.phones = phones
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.id)
