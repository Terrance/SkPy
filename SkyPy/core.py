import time
import datetime

from .conn import SkypeConnection, resubscribeOn
from .user import SkypeUser, SkypeContact, SkypeRequest
from .chat import SkypeSingleChat, SkypeGroupChat
from .event import SkypeEvent, SkypeTypingEvent, SkypeNewMessageEvent, SkypeEditMessageEvent
from .util import SkypeApiException, cacheResult, syncState

class Skype(object):
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.userId = user
        self.conn = SkypeConnection(user, pwd, tokenFile)
    @property
    @cacheResult
    def user(self):
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
        for json in self.conn("GET", "{0}/users/{1}/contacts".format(SkypeConnection.API_CONTACTS, self.userId), auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            if not json.get("suggested"):
                contacts[json.get("id")] = SkypeContact.fromRaw(self, json)
        contacts[self.userId] = self.user
        return contacts
    @cacheResult
    def getContact(self, id, full=False):
        """
        Retrieve a specific contact.  Data from contacts is used if possible, or unless full is set.

        Full details requires an extra API call, and includes fields such as birthday and mood.

        Returns None if the identifier represents a user not in the contact list.
        """
        if not full and id in self.contacts:
            return self.contacts.get(id)
        try:
            json = self.conn("GET", "{0}/users/{1}/profile".format(SkypeConnection.API_USER, id), auth=SkypeConnection.Auth.Skype).json()
            return SkypeContact.fromRaw(self, json)
        except SkypeApiException as e:
            if e.args[1].status_code == 403:
                return
            raise
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

        Note that it is not possible to distinguish if a contacts exists or not.

        An unregistered identifier produces a profile with only the identifier populated.
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
    @cacheResult
    def getChat(self, id, json=None):
        """
        Get a single conversation by identifier.  If the first API call has already been made (e.g. getChats(), use raw and skip it here.
        """
        if not json:
            json = self.conn("GET", "{0}/users/ME/conversations/{1}".format(self.conn.msgsHost, id), auth=SkypeConnection.Auth.Reg, params={"view": "msnp24Equivalent"}).json()
        if "threadProperties" in json:
            info = self.conn("GET", "{0}/threads/{1}".format(self.conn.msgsHost, json.get("id")), auth=SkypeConnection.Auth.Reg, params={"view": "msnp24Equivalent"}).json()
            json.update(info)
            return SkypeGroupChat.fromRaw(self, json)
        else:
            return SkypeSingleChat.fromRaw(self, json)
    def createChat(self, members=[], admins=[]):
        """
        Create a new group chat with the given users.
        """
        members = [{
            "id": "8:{0}".format(self.userId),
            "role": "Admin"
        }] + [{
            "id": "8:{0}".format(id),
            "role": "User"
        } for id in members if id not in admins] + [{
            "id": "8:{0}".format(id),
            "role": "Admin"
        } for id in admins]
        resp = self.conn("POST", "{0}/threads".format(self.conn.msgsHost), auth=SkypeConnection.Auth.Reg, json={"members": members})
        return self.getChat(resp.headers["Location"].rsplit("/", 1)[1])
    def getRequests(self):
        """
        Retrieve a list of pending contact requests.
        """
        json = self.conn("GET", "{0}/users/self/contacts/auth-request".format(SkypeConnection.API_USER), auth=SkypeConnection.Auth.Skype).json()
        requests = []
        for obj in json:
            requests.append(SkypeRequest.fromRaw(self, obj))
        return requests
    @resubscribeOn(400, 404)
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
                elif msgType in ("Text", "RichText", "RichText/Contacts", "RichText/UriObject"):
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
    def setAvatar(self, file):
        """
        Update the profile picture for the current user.
        """
        self.conn("PUT", "{0}/users/{1}/profile/avatar".format(SkypeConnection.API_USER, self.userId), auth=SkypeConnection.Auth.Skype, data=file.read())
    def __str__(self):
        return "[{0}]\nUserId: {1}".format(self.__class__.__name__, str(self.userId).replace("\n", "\n" + (" " * 6)))
    def __repr__(self):
        return "{0}(userId={1})".format(self.__class__.__name__, repr(self.userId))
