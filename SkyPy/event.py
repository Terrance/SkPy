import datetime
import re

from .conn import SkypeConnection

from .util import SkypeObj, userToId, chatToId, lazyLoad
class SkypeEvent(SkypeObj):
    attrs = ["id", "time", "type"]
    def __init__(self, skype, raw):
        self.skype = skype
        self.raw = raw
        self.id = raw.get("id")
        self.time = datetime.datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%SZ")
        self.type = raw.get("resourceType")
    def ack(self):
        if "ackrequired" in self.raw.get("resource"):
            self.skype.conn("POST", self.res.get("ackrequired"), auth=SkypeConnection.Auth.Reg)

class SkypePresenceEvent(SkypeEvent):
    attrs = SkypeEvent.attrs + ["userId", "status"]
    def __init__(self, skype, raw):
        super(SkypePresenceEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.userId = userToId(raw.get("resourceLink"))
        self.status = res.get("status")
    @property
    @lazyLoad
    def user(self):
        return self.skype.contacts.get(self.userId)

class SkypeTypingEvent(SkypeEvent):
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
        return self.skype.contacts.get(self.userId)
    @property
    @lazyLoad
    def chat(self):
        return self.skype.chats.get(self.chatId)

class SkypeMessageEvent(SkypeEvent):
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
        return self.skype.contacts.get(self.userId)
    @property
    @lazyLoad
    def chat(self):
        return self.skype.chats.get(self.chatId)

class SkypeNewMessageEvent(SkypeMessageEvent):
    def __init__(self, skype, raw):
        super(SkypeNewMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.content = res.get("content")

class SkypeEditMessageEvent(SkypeMessageEvent):
    attrs = SkypeMessageEvent.attrs + ["editId"]
    def __init__(self, skype, raw):
        super(SkypeEditMessageEvent, self).__init__(skype, raw)
        res = raw.get("resource", {})
        self.editId = int(res.get("skypeeditedid"))
        self.content = res.get("content")
