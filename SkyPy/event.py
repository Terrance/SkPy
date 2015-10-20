import datetime
import re

from .conn import SkypeConnection
from .util import SkypeObj, userToId, chatToId, lazyLoad

class SkypeEvent(SkypeObj):
    """
    The base Skype event.  Pulls out common identifier, time and type parameters.
    """
    attrs = ["id", "time", "type"]
    def __init__(self, skype, raw):
        self.skype = skype
        self.raw = raw
        self.id = raw.get("id")
        self.time = datetime.datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%SZ")
        self.type = raw.get("resourceType")
    def ack(self):
        """
        Acknowledge receipt of an event, if a response is required.
        """
        if "ackrequired" in self.raw.get("resource"):
            self.skype.conn("POST", self.res.get("ackrequired"), auth=SkypeConnection.Auth.Reg)

class SkypePresenceEvent(SkypeEvent):
    """
    An event for contacts changing status.
    """
    attrs = SkypeEvent.attrs + ["userId", "status"]
    def __init__(self, skype, raw):
        super(SkypePresenceEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.userId = userToId(raw.get("resourceLink"))
        self.status = res.get("status")
    @property
    @lazyLoad
    def user(self):
        """
        Lazy: retrieve the user referred to in the event.
        """
        return self.skype.contacts.get(self.userId)

class SkypeTypingEvent(SkypeEvent):
    """
    An event for users starting or stopping typing in a conversation.
    """
    attrs = SkypeEvent.attrs + ["user", "chat", "active"]
    def __init__(self, skype, raw):
        super(SkypeTypingEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.userId = userToId(res.get("from"))
        self.chatId = chatToId(res.get("conversationLink"))
        self.active = (res.get("messagetype") == "Control/Typing")
    @property
    @lazyLoad
    def user(self):
        """
        Lazy: retrieve the user referred to in the event.
        """
        return self.skype.contacts.get(self.userId)
    @property
    @lazyLoad
    def chat(self):
        """
        Lazy: retrieve the conversation referred to in the event.
        """
        return self.skype.chats.get(self.chatId)

class SkypeMessageEvent(SkypeEvent):
    """
    The base message event, when a message is received in a conversation.
    """
    attrs = SkypeEvent.attrs + ["msgId", "user", "chat", "content"]
    def __init__(self, skype, raw):
        super(SkypeMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.msgId = int(res.get("id"))
        self.userId = userToId(res.get("from"))
        self.chatId = chatToId(res.get("conversationLink"))
    @property
    @lazyLoad
    def user(self):
        """
        Lazy: retrieve the user referred to in the event.
        """
        return self.skype.contacts.get(self.userId)
    @property
    @lazyLoad
    def chat(self):
        """
        Lazy: retrieve the conversation referred to in the event.
        """
        return self.skype.chats.get(self.chatId)

class SkypeNewMessageEvent(SkypeMessageEvent):
    """
    An event for a new message being received in a conversation.
    """
    def __init__(self, skype, raw):
        super(SkypeNewMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.content = res.get("content")

class SkypeEditMessageEvent(SkypeMessageEvent):
    """
    An event for the update of an existing message in a conversation.
    """
    attrs = SkypeMessageEvent.attrs + ["editId"]
    def __init__(self, skype, raw):
        super(SkypeEditMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.editId = int(res.get("skypeeditedid"))
        self.content = res.get("content")
