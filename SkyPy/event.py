import datetime
import re

class SkypeEvent(object):
    def __init__(self, raw):
        self.id = raw["id"]
        self.time = datetime.datetime.strptime(raw["time"], "%Y-%m-%dT%H:%M:%SZ")
        self.type = raw["resourceType"]
        self.raw = raw
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.id)

class SkypePresenceEvent(SkypeEvent):
    def __init__(self, raw):
        super(self.__class__, self).__init__(raw)
        self.user = userUrlToId(raw["resourceLink"])
        self.status = raw["resource"].get("status")

class SkypeMessageEvent(SkypeEvent):
    def __init__(self, raw):
        super(self.__class__, self).__init__(raw)
        self.msgId = int(raw["resource"].get("id"))
        self.editId = int(raw["resource"].get("skypeeditedid")) if "skypeeditedid" in raw["resource"] else None
        self.sender = userUrlToId(raw["resource"].get("from"))
        self.body = raw["resource"].get("content")

def userUrlToId(url):
    match = re.search(r"/v1/users/ME/contacts/8:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None
