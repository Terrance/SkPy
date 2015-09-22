import datetime
import re

from .conn import SkypeConnection
from .util import objToStr, userToId, chatToId

class SkypeEvent(object):
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
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.id)

class SkypePresenceEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(self.__class__, self).__init__(raw, skype)
        self.user = skype.contacts[userToId(raw["resourceLink"])]
        self.status = raw["resource"].get("status")
    def __str__(self):
        return objToStr(self, "id", "time", "type", "user", "status")

class SkypeTypingEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(self.__class__, self).__init__(raw, skype)
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.active = (raw["resource"].get("messagetype") == "Control/Typing")
        self.chat = chatToId(raw["resource"].get("conversationLink"))
    def __str__(self):
        return objToStr(self, "id", "time", "type", "user", "active", "chat")

class SkypeMessageEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(self.__class__, self).__init__(raw, skype)
        self.msgId = int(raw["resource"].get("id"))
        if "skypeeditedid" in raw["resource"]:
            if "content" in raw["resource"]:
                self.editId = int(raw["resource"].get("skypeeditedid"))
                self.body = raw["resource"].get("content")
            else:
                self.deleteId = int(raw["resource"].get("skypeeditedid"))
        else:
            self.body = raw["resource"].get("content")
        self.user = skype.contacts[userToId(raw["resource"].get("from"))]
        self.chat = chatToId(raw["resource"].get("conversationLink"))
    def __str__(self):
        return objToStr(self, "id", "time", "type", "msgId", "editId", "user", "chat", "body")
