import time
import datetime

from .conn import SkypeConnection, resubscribeOn
from .chat import SkypeUser, SkypeContact, SkypeRequest, SkypeSingleChat, SkypeGroupChat
from .event import SkypeEvent, SkypeTypingEvent, SkypeNewMessageEvent, SkypeEditMessageEvent
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
        json = self.conn("GET", "{0}/users/self/profile".format(SkypeConnection.API_USER), auth=SkypeConnection.Auth.Skype).json()
        return SkypeContact.fromRaw(self, json)
    @property
    @cacheResult
    def contacts(self):
        """
        Retrieve all contacts for the current user.  Note that full details on each contact are not provided, this requires a further call to getContact().
        """
        contacts = {}
        for json in self.conn("GET", "{0}/users/{1}/contacts".format(SkypeConnection.API_CONTACTS, self.me.id), auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            if not json.get("suggested"):
                contacts[json.get("id")] = SkypeContact.fromRaw(self, json)
        contacts[self.me.id] = self.me
        return contacts
    @cacheResult
    def getContact(self, id):
        """
        Get full information about a contact.
        """
        json = self.conn("GET", "{0}/users/{1}/profile".format(SkypeConnection.API_USER, id), auth=SkypeConnection.Auth.Skype).json()
        return SkypeContact.fromRaw(self, json)
    @cacheResult
    def searchUsers(self, query):
        """
        Search the Skype Directory for a user.
        """
        json = self.conn("GET", "{0}/search/users/any".format(SkypeConnection.API_USER), auth=SkypeConnection.Auth.Skype, params={
            "keyWord": query,
            "contactTypes[]": "skype"
        }).json()
        results = []
        for obj in json:
            res = obj.get("ContactCards", {}).get("Skype")
            # Make result data nesting a bit cleaner.
            res["Location"] = obj.get("ContactCards", {}).get("CurrentLocation")
            results.append(res)
        return results
    @cacheResult
    def getUser(self, id):
        """
        Get information about a user, without them being a contact.
        """
        json = self.conn("POST", "{0}/users/self/contacts/profiles".format(SkypeConnection.API_USER), auth=SkypeConnection.Auth.Skype, data={"contacts[]": id}).json()
        return SkypeUser.fromRaw(self, json[0])
    @syncState
    def getChats(self):
        """
        Retrieve a list of recent conversations.

        Each conversation is only retrieved once, so subsequent calls may exhaust the set and return an empty list.
        """
        url = "{0}/users/ME/conversations".format(self.conn.msgsHost)
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
                chats[json.get("id")] = self.getChat(json.get("id"), json)
            return chats
        return url, params, fetch, process
    def getChat(self, id, json=None):
        """
        Get a single conversation by identifier.  If the first API call has already been made (e.g. getChats(), use raw and skip it here.
        """
        if not json:
            json = self.conn("GET", "{0}/users/ME/conversations/{1}".format(self.conn.msgsHost, id), auth=SkypeConnection.Auth.Reg, params={"view": "msnp24Equivalent"}).json()
        if "threadProperties" in json:
            # ...this doesn't need authentication?
            info = self.conn("GET", "{0}/threads/{1}".format(self.conn.msgsHost, json.get("id")), params={"view": "msnp24Equivalent"}).json()
            json.update(info)
            return SkypeGroupChat.fromRaw(self, json)
        else:
            return SkypeSingleChat.fromRaw(self, json)
    def getRequests(self):
        """
        Retrieve a list of pending contact requests.
        """
        json = self.conn("GET", "{0}/users/self/contacts/auth-request".format(SkypeConnection.API_USER), auth=SkypeConnection.Auth.Skype).json()
        requests = []
        for obj in json:
            requests.append(SkypeRequest.fromRaw(self, obj))
        return requests
    @resubscribeOn(404)
    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events are currently available, the API will block for up to 30 seconds, after which an empty list is returned.

        If any event occurs whilst blocked, it is returned immediately.
        """
        events = []
        for json in self.conn("POST", "{0}/users/ME/endpoints/SELF/subscriptions/0/poll".format(self.conn.msgsHost), auth=SkypeConnection.Auth.Reg).json().get("eventMessages", []):
            resType = json.get("resourceType")
            res = json.get("resource", {})
            if resType == "NewMessage":
                msgType = res.get("messagetype")
                if msgType in ("Control/Typing", "Control/ClearTyping"):
                    ev = SkypeTypingEvent.fromRaw(self, json)
                elif msgType in ("Text", "RichText"):
                    if res.get("skypeeditedid"):
                        ev = SkypeEditMessageEvent.fromRaw(self, json)
                    else:
                        ev = SkypeNewMessageEvent.fromRaw(self, json)
                else:
                    ev = SkypeEvent.fromRaw(self, json)
            else:
                ev = SkypeEvent.fromRaw(self, json)
            events.append(ev)
        return events
    def setPresence(self, online=True):
        """
        Set the user's presence (either Online or Hidden).
        """
        self.conn("PUT", "{0}/users/ME/presenceDocs/messagingService".format(self.conn.msgsHost), auth=SkypeConnection.Auth.Reg, json={
            "status": "Online" if online else "Hidden"
        })
    def __str__(self):
        return "[{0}]\nUser: {1}".format(self.__class__.__name__, str(self.me).replace("\n", "\n" + (" " * 6)))
    def __repr__(self):
        return "{0}(user={1})".format(self.__class__.__name__, repr(self.me))
