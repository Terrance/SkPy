import datetime
import re

from .conn import SkypeConnection
from .util import SkypeObj, userToId, chatToId, cacheResult

class SkypeEvent(SkypeObj):
    """
    The base Skype event.  Pulls out common identifier, time and type parameters.
    """
    attrs = ["id", "time", "type"]
    def __init__(self, skype, raw):
        self.skype = skype
        self.raw = raw
        self.id = raw.get("id")
        self.time = datetime.datetime.strptime(raw.get("time"), "%Y-%m-%dT%H:%M:%SZ") if "time" in raw else None
        self.type = raw.get("resourceType")
    def ack(self):
        """
        Acknowledge receipt of an event, if a response is required.
        """
        url = self.raw.get("resource", {}).get("ackrequired")
        if url:
            self.skype.conn("POST", url, auth=SkypeConnection.Auth.Reg)

class SkypePresenceEvent(SkypeEvent):
    """
    An event for contacts changing status.
    """
    attrs = SkypeEvent.attrs + ["userId", "status"]
    def __init__(self, skype, raw):
        super(SkypePresenceEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.userId = userToId(raw.get("resourceLink", ""))
        self.status = res.get("status")
    @property
    def user(self):
        """
        Retrieve the user referred to in the event.
        """
        return self.skype.getContact(self.userId)

class SkypeTypingEvent(SkypeEvent):
    """
    An event for users starting or stopping typing in a conversation.
    """
    attrs = SkypeEvent.attrs + ["user", "chat", "active"]
    def __init__(self, skype, raw):
        super(SkypeTypingEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.userId = userToId(res.get("from", ""))
        self.chatId = chatToId(res.get("conversationLink", ""))
        self.active = (res.get("messagetype") == "Control/Typing")
    @property
    def user(self):
        """
        Retrieve the user referred to in the event.
        """
        return self.skype.getContact(self.userId)
    @property
    def chat(self):
        """
        Retrieve the conversation referred to in the event.
        """
        return self.skype.getChat(self.chatId)

class SkypeMessageEvent(SkypeEvent):
    """
    The base message event, when a message is received in a conversation.
    """
    attrs = SkypeEvent.attrs + ["msgId", "user", "chat", "content"]
    def __init__(self, skype, raw):
        super(SkypeMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.msgId = int(res.get("id")) if "id" in res else None
        self.userId = userToId(res.get("from", ""))
        self.chatId = chatToId(res.get("conversationLink", ""))
    @property
    def user(self):
        """
        Retrieve the user referred to in the event.
        """
        return self.skype.getContact(self.userId)
    @property
    def chat(self):
        """
        Retrieve the conversation referred to in the event.
        """
        return self.skype.getChat(self.chatId)

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
