import time
import datetime

from .conn import SkypeConnection
from .util import SkypeObj

class SkypeUser(SkypeObj):
    attrs = ["id", "isMe", "type", "authorised", "blocked", "name", "location", "phones", "avatar"]
    def __init__(self, skype, raw, isMe=False):
        super(SkypeUser, self).__init__(skype, raw)
        self.isMe = isMe
        if isMe:
            self.attrs = ["id", "isMe", "name", "location", "language", "phones", "avatar"]
            self.id = raw.get("username")
            self.name = {
                "first": raw.get("firstname"),
                "last": raw.get("lastname")
            }
            self.location = {
                "city": raw.get("city"),
                "state": raw.get("province"),
                "country": raw.get("country")
            }
            self.language = raw.get("language")
            self.phones = []
            for k in ("Home", "Mobile", "Office"):
                if raw.get("phone" + k):
                    self.phones.append(raw.get("phone" + k))
        else:
            self.id = raw.get("id")
            self.type = raw.get("type")
            self.authorised = raw.get("authorized")
            self.blocked = raw.get("blocked")
            self.name = raw.get("name")
            self.location = raw.get("locations")[0] if "locations" in raw else {}
            self.phones = raw.get("phones") or []
        self.avatar = raw.get("avatar_url")
    def getChat(self):
        return SkypeChat(self.skype.conn, self.skype.conn("GET", self.skype.conn.msgsHost + "/conversations/8:" + self.id, auth=SkypeConnection.Auth.Reg, params={"view": "msnp24Equivalent"}).json())

class SkypeChat(SkypeObj):
    attrs = ["id"]
    def __init__(self, skype, raw):
        super(SkypeChat, self).__init__(skype, raw)
        self.id = raw.get("id")
    def getMsgs(self):
        resp = self.skype.conn("GET", self._msgSyncState if hasattr(self, "_msgSyncState") else self.skype.conn.msgsHost + "/conversations/" + self.id + "/messages", auth=SkypeConnection.Auth.Reg, params={
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }).json()
        self._msgSyncState = resp.get("_metadata", {}).get("syncState")
        msgs = []
        for json in resp.get("messages", []):
            msgs.append(SkypeMsg(self.skype.conn, json))
        return msgs
    def sendMsg(self, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = self.skype.conn("POST", self.skype.conn.msgsHost + "/conversations/" + self.id + "/messages", auth=SkypeConnection.Auth.Reg, json={
            "skypeeditedid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        return msgId

class SkypeMsg(SkypeObj):
    attrs = ["id", "type", "content"]
    def __init__(self, skype, raw):
        super(SkypeMsg, self).__init__(skype, raw)
        self.id = raw.get("id")
        self.oldMsgId = raw.get("skypeeditedid")
        self.time = datetime.datetime.strptime(raw.get("originalarrivaltime"), "%Y-%m-%dT%H:%M:%S.%fZ")
        self.type = raw.get("messagetype")
        self.content = raw.get("content")
