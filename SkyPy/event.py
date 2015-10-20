import datetime
import re

from .conn import SkypeConnection
from .util import SkypeObj, userToId, chatToId

class SkypeEvent(SkypeObj):
    attrs = ["id", "time", "type"]
    def __init__(self, skype, raw):
        self.id = raw["id"]
        self.time = datetime.datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%SZ")
        self.type = raw["resourceType"]
        self.raw = raw
        self.skype = skype
    def ack(self):
        if "ackrequired" in self.raw["resource"]:
            self.skype.conn("POST", self.raw["resource"]["ackrequired"], auth=SkypeConnection.Auth.Reg)

class SkypePresenceEvent(SkypeEvent):
    attrs = SkypeEvent.attrs + ["user", "status"]
    def __init__(self, skype, raw):
        super(SkypePresenceEvent, self).__init__(skype, raw)
        self.user = skype.contacts[userToId(raw["resourceLink"])]
        self.status = raw["resource"].get("status")

class SkypeTypingEvent(SkypeEvent):
    attrs = SkypeEvent.attrs + ["user", "active", "chat"]
    def __init__(self, skype, raw):
        super(SkypeTypingEvent, self).__init__(skype, raw)
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.active = (raw["resource"].get("messagetype") == "Control/Typing")
        self.chat = skype.chats[chatToId(raw["resource"].get("conversationLink"))]

class SkypeMessageEvent(SkypeEvent):
    attrs = SkypeEvent.attrs + ["msgId", "user", "chat", "content"]
    def __init__(self, skype, raw):
        super(SkypeMessageEvent, self).__init__(skype, raw)
        self.msgId = int(raw["resource"].get("id"))
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.chat = skype.chats[chatToId(raw["resource"].get("conversationLink"))]
        self.content = None

class SkypeNewMessageEvent(SkypeMessageEvent):
    def __init__(self, skype, raw):
        super(SkypeNewMessageEvent, self).__init__(skype, raw)
        self.content = raw["resource"].get("content")

class SkypeEditMessageEvent(SkypeMessageEvent):
    attrs = SkypeMessageEvent.attrs + ["editId"]
    def __init__(self, skype, raw):
        super(SkypeEditMessageEvent, self).__init__(skype, raw)
        self.editId = int(raw["resource"].get("skypeeditedid"))
        self.content = raw["resource"].get("content")

class SkypeDeleteMessageEvent(SkypeMessageEvent):
    attrs = SkypeMessageEvent.attrs + ["deleteId"]
    def __init__(self, skype, raw):
        super(SkypeDeleteMessageEvent, self).__init__(skype, raw)
        self.deleteId = int(raw["resource"].get("skypeeditedid"))
