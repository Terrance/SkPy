import datetime
import re

from .conn import SkypeConnection

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
        self.user = userToId(raw["resourceLink"])
        self.status = raw["resource"].get("status")
    def __str__(self):
        return objToStr(self, "id", "time", "type", "user", "status")

class SkypeTypingEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(self.__class__, self).__init__(raw, skype)
        self.sender = userToId(raw["resource"].get("from"))
        self.active = (raw["resource"].get("messagetype") == "Control/Typing")
        self.chat = chatToId(raw["resource"].get("conversationLink"))
    def __str__(self):
        return objToStr(self, "id", "time", "type", "sender", "active", "chat")

class SkypeMessageEvent(SkypeEvent):
    def __init__(self, raw, skype):
        super(self.__class__, self).__init__(raw, skype)
        self.msgId = int(raw["resource"].get("id"))
        self.editId = int(raw["resource"].get("skypeeditedid")) if "skypeeditedid" in raw["resource"] else None
        self.sender = userToId(raw["resource"].get("from"))
        self.chat = chatToId(raw["resource"].get("conversationLink"))
        self.body = raw["resource"].get("content")
    def __str__(self):
        return objToStr(self, "id", "time", "type", "msgId", "editId", "sender", "chat", "body")

def userToId(url):
    match = re.search(r"/v1/users/ME/contacts/8:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None

def chatToId(url):
    match = re.search(r"/v1/users/ME/conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None

def objToStr(obj, *attrs):
    out = "[{0}]".format(obj.__class__.__name__)
    for attr in attrs:
        out += "\n{0}: {1}".format(attr.capitalize(), str(getattr(obj, attr)).replace("\n", "\n  " + (" " * len(attr))))
    return out
