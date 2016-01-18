import time
import datetime

import requests

from .conn import SkypeConnection
from .user import SkypeContact, SkypeContacts, SkypeRequest
from .chat import SkypeSingleChat, SkypeGroupChat, SkypeChats
from .event import SkypeEvent
from .util import SkypeObj, cacheResult, syncState

class Skype(SkypeObj):
    attrs = ("userId",)
    """
    The main Skype instance.  Provides methods for retrieving various other object types.
    """
    def __init__(self, user=None, pwd=None, tokenFile=None):
        """
        Create a new Skype object and corresponding connection.

        All arguments are passed to the SkypeConnection class.
        """
        self.conn = SkypeConnection(user, pwd, tokenFile)
        self.userId = self.conn.user
        self.contacts = SkypeContacts(self)
        self.chats = SkypeChats(self)
    @property
    @cacheResult
    def user(self):
        """
        Retrieve the current user.
        """
        json = self.conn("GET", "{0}/users/self/profile".format(SkypeConnection.API_USER),
                         auth=SkypeConnection.Auth.Skype).json()
        return SkypeContact.fromRaw(self, json)
    @SkypeConnection.handle(404, regToken=True)
    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events occur, the API will block for up to 30 seconds, after which an empty list is returned.

        If any event occurs whilst blocked, it is returned immediately.
        """
        events = []
        for json in self.conn.endpoints["self"].getEvents():
            events.append(SkypeEvent.fromRaw(self, json))
        return events
    def setPresence(self, online=True):
        """
        Set the user's presence (either Online or Hidden).
        """
        self.conn("PUT", "{0}/users/ME/presenceDocs/messagingService".format(self.conn.msgsHost),
                  auth=SkypeConnection.Auth.Reg, json={"status": "Online" if online else "Hidden"})
    def setAvatar(self, file):
        """
        Update the profile picture for the current user.
        """
        self.conn("PUT", "{0}/users/{1}/profile/avatar".format(SkypeConnection.API_USER, self.userId),
                  auth=SkypeConnection.Auth.Skype, data=file.read())

class SkypeEventLoop(Skype):
    """
    A skeleton class for producting event processing programs.

    Implementors should override the onEvent(event) method to react to messages and status changes.
    """
    def __init__(self, user=None, pwd=None, tokenFile=None, autoAck=True):
        super(SkypeEventLoop, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck
    def loop(self):
        """
        Handle any incoming events.  If autoAck is set, any 'ackrequired' URLs are automatically called.
        """
        while True:
            try:
                events = self.getEvents();
            except requests.ConnectionError:
                continue
            for event in events:
                self.onEvent(event)
                if self.autoAck:
                    event.ack()
    def onEvent(self, event):
        pass
