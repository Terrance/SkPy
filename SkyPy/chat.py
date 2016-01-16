from time import time
from datetime import datetime

from .conn import SkypeConnection
from .msg import SkypeMsg, SkypeContactMsg, SkypeFileMsg, SkypeImageMsg
from .util import SkypeObj, noPrefix, initAttrs, convertIds, cacheResult, syncState

@initAttrs
class SkypeChat(SkypeObj):
    """
    A conversation within Skype.

    One-to-one chats have identifiers of the form <type>:<username>.

    Cloud group chat identifiers are of the form <type>:<identifier>@thread.skype.
    """
    attrs = ("id",)
    @classmethod
    def rawToFields(cls, raw={}):
        return {
            "id": raw.get("id")
        }
    @syncState
    def getMsgs(self):
        """
        Retrieve any new messages in the conversation.

        On first access, this method should be repeatedly called to retrieve older messages.
        """
        url = "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id)
        params = {
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }
        def fetch(url, params):
            resp = self.skype.conn("GET", url, auth=SkypeConnection.Auth.Reg, params=params).json()
            return resp, resp.get("_metadata", {}).get("syncState")
        def process(resp):
            msgs = []
            for json in resp.get("messages", []):
                msgs.append(SkypeMsg.fromRaw(self.skype, json))
            return msgs
        return url, params, fetch, process
    def sendMsg(self, content, me=False, rich=False, edit=None):
        """
        Send a message to the conversation.

        If me is specified, the message is sent as an action (similar to "/me ...", where /me becomes your name).

        Set rich to allow formatting tags -- use the SkypeMsg static helper methods for rich components.

        If edit is specified, perform an edit (or delete if content is empty) of the message with that identifier.
        """
        timeId = int(time())
        msgId = edit or timeId
        msgType = "RichText" if rich else "Text"
        msgRaw = {
            ("skypeeditedid" if edit else "clientmessageid"): msgId,
            "messagetype": msgType,
            "contenttype": "text",
            "content": content
        }
        if me:
            name = str(self.skype.user.name)
            msgRaw.update({
                "messagetype": "Text",
                "content": "{0} {1}".format(name, content),
                "imdisplayname": name,
                "skypeemoteoffset": len(name) + 1
            })
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, json=msgRaw)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        editId = msgId if edit else None
        return SkypeMsg(self.skype, id=timeId, type=msgType, time=timeStr, editId=editId,
                        userId=self.skype.user.id, chatId=self.id, content=content)
    def sendFile(self, content, name, image=False):
        """
        Upload a file to the conversation.  Content should be an ASCII or binary file-like object.

        If an image, Skype will generate a thumbnail and link to the full image.
        """
        meta = {
            "type": "pish/image" if image else "sharing/file",
            "permissions": dict(("8:{0}".format(id), ["read"]) for id in self.userIds)
        }
        if not image:
            meta["filename"] = name
        objId = self.skype.conn("POST", "https://api.asm.skype.com/v1/objects",
                                auth=SkypeConnection.Auth.Authorize, json=meta).json()["id"]
        objType = "imgpsh" if image else "original"
        self.skype.conn("PUT", "https://api.asm.skype.com/v1/objects/{0}/content/{1}".format(objId, objType),
                        auth=SkypeConnection.Auth.Authorize, data=content.read())
        size = content.tell()
        if image:
            body = """<URIObject type="Picture.1" uri="https://api.asm.skype.com/v1/objects/{0}" """ \
                   """url_thumbnail="https://api.asm.skype.com/v1/objects/{0}/views/imgt1">MyLegacy pish """ \
                   """<a href="https://api.asm.skype.com/s/i?{0}">https://api.asm.skype.com/s/i?{0}</a>""" \
                   """<Title/><Description/><OriginalName v="{1}"/>""" \
                   """<meta type="photo" originalName="{1}"/></URIObject>""".format(objId, name)
        else:
            body = """<URIObject type="File.1" uri="https://api.asm.skype.com/v1/objects/{0}" """ \
                   """url_thumbnail="https://api.asm.skype.com/v1/objects/{0}/views/thumbnail">""" \
                   """<Title>Title: {1}</Title><Description> Description: {1}</Description>""" \
                   """<a href="https://login.skype.com/login/sso?go=webclient.xmm&amp;docid={0}"> """ \
                   """https://login.skype.com/login/sso?go=webclient.xmm&amp;docid={0}</a>""" \
                   """<OriginalName v="{1}"/><FileSize v="{2}"/></URIObject>""".format(objId, name, size)
        msg = {
            "clientmessageid": int(time()),
            "contenttype": "text",
            "messagetype": "RichText/{0}".format("UriObject" if image else "Media_GenericFile"),
            "content": body
        }
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, json=msg)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        if image:
            return SkypeImageMsg(self.skype, id=msg["clientmessageid"], type=msg["messagetype"], time=timeStr,
                                 userId=self.skype.user.id, chatId=self.id, content=msg["content"], fileName=name,
                                 fileUrlFull="https://api.asm.skype.com/v1/objects/{0}".format(objId),
                                 fileUrlThumb="https://api.asm.skype.com/v1/objects/{0}/views/imgtl".format(objId),
                                 fileUrlView="https://api.asm.skype.com/s/i?{0}".format(objId))
        else:
            return SkypeFileMsg(self.skype, id=msg["clientmessageid"], type=msg["messagetype"], time=timeStr,
                                userId=self.skype.user.id, chatId=self.id, content=msg["content"], fileName=name,
                                fileSize=size, fileUrlFull="https://api.asm.skype.com/v1/objects/{0}".format(objId),
                                fileUrlThumb="https://api.asm.skype.com/v1/objects/{0}/views/thumbnail".format(objId),
                                fileUrlView="https://login.skype.com/login/sso?go=webclient.xmm&docid={0}".format(objId))
    def sendContact(self, contact):
        """
        Share a contact with the conversation.
        """
        msg = {
            "clientmessageid": int(time()),
            "messagetype": "RichText/Contacts",
            "contenttype": "text",
            "content": """<contacts><c t="s" s="{0}" f="{1}"/></contacts>""".format(contact.id, contact.name)
        }
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, json=msg)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        return SkypeContactMsg(self.skype, id=msg["clientmessageid"], type=msg["messagetype"],
                               time=timeStr, userId=self.skype.user.id, chatId=self.id,
                               content=msg["content"], contactId=contact.id, contactName="{0}".format(contact.name))
    def delete(self):
        """
        Delete the conversation and all message history.
        """
        self.skype.conn("DELETE", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg)

@initAttrs
@convertIds("user", "users")
class SkypeSingleChat(SkypeChat):
    """
    A one-to-one conversation within Skype.  Has an associated user for the other participant.
    """
    attrs = SkypeChat.attrs + ("userId",)
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeSingleChat, cls).rawToFields(raw)
        fields["userId"] = noPrefix(fields.get("id"))
        return fields
    @property
    def userIds(self):
        """
        Convenience method to treat and single and group chats alike.
        """
        return [self.userId]

@initAttrs
@convertIds("users", user=("creator",))
class SkypeGroupChat(SkypeChat):
    """
    A group conversation within Skype.  Compared to single chats, groups have a topic and participant list.
    """
    attrs = SkypeChat.attrs + ("topic", "creatorId", "userIds", "open", "history", "picture")
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeGroupChat, cls).rawToFields(raw)
        props = raw.get("properties", {})
        userIds = []
        for obj in raw.get("members"):
            userIds.append(noPrefix(obj.get("id")))
        fields.update({
            "topic": raw.get("threadProperties", {}).get("topic"),
            "creatorId": noPrefix(props.get("creator")),
            "userIds": userIds,
            "open": props.get("joiningenabled", "") == "true",
            "history": props.get("historydisclosed", "") == "true",
            "picture": props.get("picture", "")[4:] or None
        })
        return fields
    @property
    @cacheResult
    def joinUrl(self):
        query = {
            "baseDomain": "https://join.skype.com/launch/",
            "threadId": self.id
        }
        return self.skype.conn("POST", "{0}/threads".format(SkypeConnection.API_SCHEDULE),
                               auth=SkypeConnection.Auth.Skype, json=query).json()["JoinUrl"]
    def setTopic(self, topic):
        """
        Update the topic message.  An empty string clears the topic.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, params={"name": "topic"}, json={"topic": topic})
        self.topic = topic
    def setOpen(self, open):
        """
        Enable or disable public join links.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, params={"name": "joiningenabled"},
                        json={"joiningenabled": open})
        self.open = open
    def setHistory(self, history):
        """
        Enable or disable conversation history.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.Reg, params={"name": "historydisclosed"},
                        json={"historydisclosed": history})
        self.history = history
    def addMember(self, id, admin=False):
        """
        Add a user to the conversation, or update their user/admin status.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/members/8:{2}".format(self.skype.conn.msgsHost, self.id, id),
                        auth=SkypeConnection.Auth.Reg, json={"role": "Admin" if admin else "User"})
    def removeMember(self, id):
        """
        Remove a user from the conversation.
        """
        self.skype.conn("DELETE", "{0}/threads/{1}/members/8:{2}".format(self.skype.conn.msgsHost, self.id, id),
                        auth=SkypeConnection.Auth.Reg)
    def leave(self):
        """
        Leave the conversation.  You will lose any admin rights.

        If public joining is disabled, you may need to be re-invited in order to return.
        """
        self.removeMember(self.skype.userId)
