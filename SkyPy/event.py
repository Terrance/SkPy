from datetime import datetime
import re

from .conn import SkypeConnection
from .chat import SkypeMsg
from .util import SkypeObj, userToId, chatToId, initAttrs, convertIds, cacheResult

@initAttrs
class SkypeEvent(SkypeObj):
    """
    The base Skype event.  Pulls out common identifier, time and type parameters.
    """
    attrs = ("id", "type", "time")
    @classmethod
    def rawToFields(cls, raw={}):
        return {
            "id": raw.get("id"),
            "type": raw.get("resourceType"),
            "time": datetime.strptime(raw.get("time"), "%Y-%m-%dT%H:%M:%SZ") if "time" in raw else None
        }
    def ack(self):
        """
        Acknowledge receipt of an event, if a response is required.
        """
        url = self.raw.get("resource", {}).get("ackrequired")
        if url:
            self.skype.conn("POST", url, auth=SkypeConnection.Auth.Reg)

@initAttrs
@convertIds("user", "chat")
class SkypeTypingEvent(SkypeEvent):
    """
    An event for users starting or stopping typing in a conversation.
    """
    attrs = SkypeEvent.attrs + ("userId", "chatId", "active")
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeTypingEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({
            "userId": userToId(res.get("from", "")),
            "chatId": chatToId(res.get("conversationLink", "")),
            "active": (res.get("messagetype") == "Control/Typing")
        })
        return fields

@initAttrs
class SkypeMessageEvent(SkypeEvent):
    """
    The base message event, when a message is received in a conversation.
    """
    attrs = SkypeEvent.attrs + ("msgId",)
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeMessageEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields["msgId"] = int(res.get("id")) if "id" in res else None
        return fields
    @property
    @cacheResult
    def msg(self):
        return SkypeMsg.fromRaw(self.skype, self.raw.get("resource", {}))

@initAttrs
class SkypeNewMessageEvent(SkypeMessageEvent):
    """
    An event for a new message being received in a conversation.
    """
    pass

@initAttrs
class SkypeEditMessageEvent(SkypeMessageEvent):
    """
    An event for the update of an existing message in a conversation.
    """
    pass
