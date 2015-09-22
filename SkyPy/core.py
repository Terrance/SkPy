import time

from .conn import SkypeConnection
from .event import SkypeEvent, SkypePresenceEvent, SkypeTypingEvent, SkypeMessageEvent
from .util import objToStr

class Skype(object):
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.conn = SkypeConnection(user, pwd, tokenFile)
        self.user = self.getUser()
        self.contacts = self.getContacts()
    def getUser(self):
        json = self.conn("GET", "https://api.skype.com/users/self/displayname", auth=SkypeConnection.Auth.Skype).json()
        return SkypeUser(json, True)
    def getContacts(self):
        contacts = {}
        for json in self.conn("GET", "https://contacts.skype.com/contacts/v1/users/" + self.user.id + "/contacts", auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            contacts[json.get("id")] = SkypeUser(json)
        return contacts
    @SkypeConnection.resubscribeOn(404)
    def getEvents(self):
        events = []
        for json in self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.Auth.Reg).json().get("eventMessages", []):
            resType = json.get("resourceType")
            if resType == "UserPresence":
                ev = SkypePresenceEvent(json, self)
            elif resType == "NewMessage":
                msgType = json["resource"].get("messagetype")
                if msgType in ["Control/Typing", "Control/ClearTyping"]:
                    ev = SkypeTypingEvent(json, self)
                elif msgType == "RichText":
                    ev = SkypeMessageEvent(json, self)
                else:
                    ev = SkypeEvent(json, self)
            else:
                ev = SkypeEvent(json, self)
            events.append(ev)
        return events
    def setStatus(self, status):
        self.conn("PUT", self.conn.msgsHost + "/presenceDocs/messagingService", json={
            "status": status
        })
    def sendMsg(self, conv, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = self.conn("POST", self.conn.msgsHost + "/conversations/" + conv + "/messages", auth=SkypeConnection.Auth.Reg, json={
            "skypeeditedid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        return msgId
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.user.id)

class SkypeUser(object):
    def __init__(self, raw, isMe=False):
        if isMe:
            self.id = raw.get("username")
            self.name = {
                "first": raw.get("firstname"),
                "last": raw.get("lastname")
            }
        else:
            self.id = raw.get("id")
            self.type = raw.get("type")
            self.authorised = raw.get("authorized")
            self.blocked = raw.get("blocked")
            self.name = raw.get("name")
            self.location = raw.get("locations")[0] if "locations" in raw else None
            self.phones = raw.get("phones") or []
            self.avatar = raw.get("avatar_url")
        self.raw = raw
        self.isMe = isMe
    def __str__(self):
        attrs = [] if self.isMe else ["type", "authorised", "blocked", "location", "phones", "avatar"]
        return objToStr(self, "id", "name", *attrs)
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.id)
