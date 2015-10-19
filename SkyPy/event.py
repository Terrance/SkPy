import datetime
import re

from .conn import SkypeConnection
from .util import objToStr, userToId, chatToId, SkypeObj

class SkypeEvent(SkypeObj):
    def __init__(self, raw, skype):
        self.id = raw["id"]
        self.time = datetime.datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%SZ")
        self.type = raw["resourceType"]
        self.raw = raw
        self.skype = skype
    def ack(self):
        if "ackrequired" in self.raw["resource"]:
            self.skype.conn("POST", self.raw["resource"]["ackrequired"], auth=SkypeConnection.Auth.Reg)
    def __str__(self):
        return objToStr(self, "id", "time", "type")

class SkypePresenceEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(SkypePresenceEvent, self).__init__(raw, skype)
        self.user = skype.contacts[userToId(raw["resourceLink"])]
        self.status = raw["resource"].get("status")
    def __str__(self):
        return objToStr(self, "id", "time", "type", "user", "status")

class SkypeTypingEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(SkypeTypingEvent, self).__init__(raw, skype)
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.active = (raw["resource"].get("messagetype") == "Control/Typing")
        self.chat = chatToId(raw["resource"].get("conversationLink"))
    def __str__(self):
        return objToStr(self, "id", "time", "type", "user", "active", "chat")

class SkypeMessageEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(SkypeMessageEvent, self).__init__(raw, skype)
        self.msgId = int(raw["resource"].get("id"))
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.chat = chatToId(raw["resource"].get("conversationLink"))
    def __str__(self):
        return objToStr(self, "id", "time", "type", "msgId", "editId", "user", "chat", "body")

class SkypeNewMessageEvent(SkypeMessageEvent):
    def __init__(self, raw, skype):
        super(SkypeNewMessageEvent, self).__init__(raw, skype)
        self.body = raw["resource"].get("content")

class SkypeEditMessageEvent(SkypeMessageEvent):
    def __init__(self, raw, skype):
        super(SkypeEditMessageEvent, self).__init__(raw, skype)
        self.oldMsgId = int(raw["resource"].get("skypeeditedid"))
        self.body = raw["resource"].get("content")

class SkypeDeleteMessageEvent(SkypeMessageEvent):
    def __init__(self, raw, skype):
        super(SkypeDeleteMessageEvent, self).__init__(raw, skype)
        self.oldMsgId = int(raw["resource"].get("skypeeditedid"))
