import time
import datetime

from .conn import SkypeConnection
from .chat import SkypeUser, SkypeChat
from .event import SkypeEvent, SkypePresenceEvent, SkypeTypingEvent, SkypeMessageEvent

class Skype(object):
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.conn = SkypeConnection(user, pwd, tokenFile)
        self.user = self.getUser()
        self.contacts = self.getContacts()
        self.chats = self.getChats()
    def getUser(self):
        json = self.conn("GET", "https://api.skype.com/users/self/profile", auth=SkypeConnection.Auth.Skype).json()
        return SkypeUser(self.conn, json, True)
    def getContacts(self):
        contacts = {}
        for json in self.conn("GET", "https://contacts.skype.com/contacts/v1/users/" + self.user.id + "/contacts", auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            if not json.get("suggested"):
                contacts[json.get("id")] = SkypeUser(self.conn, json)
        if hasattr(self, "user"):
            contacts[self.user.id] = self.user
        return contacts
    def getChats(self, state=True):
        resp = self.conn("GET", self._chatSyncState if state and hasattr(self, "_chatSyncState") else self.conn.msgsHost + "/conversations", auth=SkypeConnection.Auth.Reg, params={
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }).json()
        self._chatSyncState = resp.get("_metadata", {}).get("syncState")
        chats = {}
        for json in resp.get("conversations", []):
            chats[json.get("id")] = SkypeChat(self.conn, json)
        return chats
    @SkypeConnection.resubscribeOn(404)
    def getEvents(self):
        events = []
        for json in self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.Auth.Reg).json().get("eventMessages", []):
            resType = json.get("resourceType")
            if resType == "UserPresence":
                ev = SkypePresenceEvent(json, self)
            elif resType == "NewMessage":
                msgType = json.get("resource", {}).get("messagetype")
                if msgType in ("Control/Typing", "Control/ClearTyping"):
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
    def __str__(self):
        return "[{0}]\nUser: {1}".format(self.__class__.__name__, str(self.user).replace("\n", "\n" + (" " * 6)))
    def __repr__(self):
        return "{0}(user={1})".format(self.__class__.__name__, repr(self.user))
