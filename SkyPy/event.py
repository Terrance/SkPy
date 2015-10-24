import datetime
import re

from .conn import SkypeConnection
from .chat import SkypeMsg
from .util import SkypeObj, userToId, chatToId, convertIds, cacheResult

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

@convertIds("user", "chat")
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

class SkypeMessageEvent(SkypeEvent):
    """
    The base message event, when a message is received in a conversation.
    """
    attrs = SkypeEvent.attrs + ["msg"]
    def __init__(self, skype, raw):
        super(SkypeMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.msgId = int(res.get("id")) if "id" in res else None
        self.msg = SkypeMsg(self.skype, self.raw.get("resource"))

class SkypeNewMessageEvent(SkypeMessageEvent):
    """
    An event for a new message being received in a conversation.
    """
    def __init__(self, skype, raw):
        super(SkypeNewMessageEvent, self).__init__(skype, raw)

class SkypeEditMessageEvent(SkypeMessageEvent):
    """
    An event for the update of an existing message in a conversation.
    """
    def __init__(self, skype, raw):
        super(SkypeEditMessageEvent, self).__init__(skype, raw)
