import time
import datetime

from .conn import SkypeConnection
from .chat import SkypeUser, SkypeChat
from .event import SkypeEvent, SkypePresenceEvent, SkypeTypingEvent, SkypeNewMessageEvent, SkypeEditMessageEvent
from .util import cacheResult, syncState

class Skype(object):
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.conn = SkypeConnection(user, pwd, tokenFile)
    @property
    @cacheResult
    def me(self):
        """
        Retrieve the current user.
        """
        json = self.conn("GET", "https://api.skype.com/users/self/profile", auth=SkypeConnection.Auth.Skype).json()
        return SkypeUser(self, json, True)
    @property
    @cacheResult
    def contacts(self):
        """
        Retrieve all contacts for the current user.

        The Skype API also provides suggestions within the same list -- these can be filtered by looking for authorised = True.
        """
        contacts = {}
        for json in self.conn("GET", self.conn.API_CONTACTS + "/users/" + self.me.id + "/contacts", auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            if not json.get("suggested"):
                contacts[json.get("id")] = SkypeUser(self, json)
        contacts[self.me.id] = self.me
        return contacts
    @cacheResult
    def getContact(self, id):
        """
        Get information about a contact.  Use the contacts list if already cached.
        """
        if hasattr(self, "contactsCached") and id in self.contactsCached:
            return self.contactsCached.get(id)
        json = self.conn("GET", self.conn.API_USER + "/users/" + id + "/profile", auth=SkypeConnection.Auth.Skype).json()
        return SkypeUser(self, json)
    @cacheResult
    def searchUsers(self, query):
        """
        Search the Skype Directory for a user.
        """
        json = self.conn("GET", self.conn.API_USER + "/search/users/any", auth=SkypeConnection.Auth.Skype, params={
            "keyWord": query,
            "contactTypes[]": "skype"
        }).json()
        results = []
        for obj in json:
            res = obj.get("ContactCards", {}).get("Skype")
            res["Location"] = obj.get("ContactCards", {}).get("CurrentLocation")
            results.append(res)
        return results
    @cacheResult
    def getUser(self, id):
        """
        Get information about a user, without them being a contact.
        """
        json = self.conn("POST", self.conn.API_USER + "/users/self/contacts/profiles", auth=SkypeConnection.Auth.Skype, data={"contacts[]": id}).json()
        return SkypeUser(self, json[0])
    @syncState
    def getChats(self):
        """
        Retrieve a list of recent conversations.

        Each conversation is only retrieved once, so subsequent calls may exhaust the set and return an empty list.
        """
        url = self.conn.msgsHost + "/conversations"
        params = {
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }
        def fetch(url, params):
            resp = self.conn("GET", url, auth=SkypeConnection.Auth.Reg, params=params).json()
            return resp, resp.get("_metadata", {}).get("syncState")
        def process(resp):
            chats = {}
            for json in resp.get("conversations", []):
                chats[json.get("id")] = SkypeChat(self, json)
            return chats
        return url, params, fetch, process
    @cacheResult
    def getChat(self, id):
        """
        Get a single conversation by identifier.
        """
        json = self.conn("GET", self.conn.msgsHost + "/conversations/" + id, auth=SkypeConnection.Auth.Reg, params={"view": "msnp24Equivalent"}).json()
        return SkypeChat(self, json)
    @SkypeConnection.resubscribeOn(404)
    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events are currently available, the API will block for up to 30 seconds, after which an empty list is returned.

        If any event occurs whilst blocked, it is returned immediately.
        """
        events = []
        for json in self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.Auth.Reg).json().get("eventMessages", []):
            resType = json.get("resourceType")
            res = json.get("resource", {})
            if resType == "UserPresence":
                ev = SkypePresenceEvent(self, json)
            elif resType == "NewMessage":
                msgType = res.get("messagetype")
                if msgType in ("Control/Typing", "Control/ClearTyping"):
                    ev = SkypeTypingEvent(self, json)
                elif msgType in ("Text", "RichText"):
                    if res.get("skypeeditedid"):
                        ev = SkypeEditMessageEvent(self, json)
                    else:
                        ev = SkypeNewMessageEvent(self, json)
                else:
                    ev = SkypeEvent(self, json)
            else:
                ev = SkypeEvent(self, json)
            events.append(ev)
        return events
    def setPresence(self, online=True):
        """
        Set the user's presence (either Online or Hidden).
        """
        self.conn("PUT", self.conn.msgsHost + "/presenceDocs/messagingService", auth=SkypeConnection.Auth.Reg, json={
            "status": "Online" if online else "Hidden"
        })
    def __str__(self):
        return "[{0}]\nUser: {1}".format(self.__class__.__name__, str(self.me).replace("\n", "\n" + (" " * 6)))
    def __repr__(self):
        return "{0}(user={1})".format(self.__class__.__name__, repr(self.me))
