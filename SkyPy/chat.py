from time import time
from datetime import datetime

from .conn import SkypeConnection
from .msg import SkypeMsg, SkypeContactMsg, SkypeFileMsg, SkypeImageMsg
from .util import SkypeObj, SkypeObjs, noPrefix, initAttrs, convertIds, cacheResult, syncState

@initAttrs
class SkypeChat(SkypeObj):
    """
    A conversation within Skype.

    Attributes:
        id (str):
            Unique identifier of the conversation.

            One-to-one chats have identifiers of the form ``<type>:<username>``.

            Cloud group chat identifiers are of the form ``<type>:<identifier>@thread.skype``.
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
        Retrieve a batch of messages from the conversation.

        This method can be called repeatedly to retrieve older messages.

        If new messages arrive in the meantime, they are returned first in the next batch.

        Returns:
            :class:`SkypeMsg` list: collection of messages
        """
        url = "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id)
        params = {
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }
        def fetch(url, params):
            resp = self.skype.conn("GET", url, auth=SkypeConnection.Auth.RegToken, params=params).json()
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

        If ``me`` is specified, the message is sent as an action (equivalent to ``/me <content>`` in other clients).
        This is typically displayed as "*Name* ``<content>``", where clicking the name links back to your profile.

        Rich text can also be sent, provided it is formatted using Skype's subset of HTML.  Helper methods on the
        :class:`.SkypeMsg` class can generate the necessary markup.

        Args:
            content (str): main message body
            me (bool): whether to send as an action, where the current account's name prefixes the message
            rich (bool): whether to send with rich text formatting
            edit (int): identifier of an existing message to edit
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
                        auth=SkypeConnection.Auth.RegToken, json=msgRaw)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        editId = msgId if edit else None
        return SkypeMsg(self.skype, id=timeId, type=msgType, time=timeStr, editId=editId,
                        userId=self.skype.user.id, chatId=self.id, content=content)
    def sendFile(self, content, name, image=False):
        """
        Upload a file to the conversation.  Content should be an ASCII or binary file-like object.

        If an image, Skype will generate a thumbnail and link to the full image.

        Args:
            content (file): file-like object to retrieve the attachment's body
            name (str): filename displayed to other clients
            image (bool): whether to treat the file as an image
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
        urlFull = "https://api.asm.skype.com/v1/objects/{0}".format(objId)
        self.skype.conn("PUT", "{0}/content/{1}".format(urlFull, objType),
                        auth=SkypeConnection.Auth.Authorize, data=content.read())
        size = content.tell()
        if image:
            body = """<URIObject type="Picture.1" uri="{1}" url_thumbnail="{1}/views/imgt1">MyLegacy pish """ \
                   """<a href="https://api.asm.skype.com/s/i?{0}">https://api.asm.skype.com/s/i?{0}</a>""" \
                   """<Title/><Description/><OriginalName v="{2}"/>""" \
                   """<meta type="photo" originalName="{2}"/></URIObject>""".format(objId, urlFull, name)
        else:
            urlView = "https://login.skype.com/login/sso?go=webclient.xmm&docid={0}".format(objId)
            body = """<URIObject type="File.1" uri="{1}" url_thumbnail="{1}/views/thumbnail">""" \
                   """<Title>Title: {3}</Title><Description> Description: {3}</Description>""" \
                   """<a href="{2}"> {2}</a><OriginalName v="{3}"/><FileSize v="{4}"/></URIObject>""" \
                   .format(objId, urlFull, urlLogin, name, size)
        msg = {
            "clientmessageid": int(time()),
            "contenttype": "text",
            "messagetype": "RichText/{0}".format("UriObject" if image else "Media_GenericFile"),
            "content": body
        }
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, json=msg)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        if image:
            msgCls = SkypeImageMsg
            msgFile = SkypeFileMsg.File(self.skype, name=name, urlFull=urlFull,
                                        urlThumb="{0}/views/imgtl".format(urlFull),
                                        urlView="https://api.asm.skype.com/s/i?{0}".format(objId))
        else:
            msgCls = SkypeFileMsg
            msgFile = SkypeFileMsg.File(self.skype, name=name, size=size, urlFull=urlFull,
                                        urlThumb="{0}/views/thumbnail".format(urlFull), urlView=urlView)
        return msgCls(self.skype, id=msg["clientmessageid"], type=msg["messagetype"], time=timeStr,
                      userId=self.skype.user.id, chatId=self.id, content=msg["content"], file=msgFile)
    def sendContact(self, contact):
        """
        Share a contact with the conversation.

        Args:
            contact (SkypeUser): the user to embed in the message
        """
        msg = {
            "clientmessageid": int(time()),
            "messagetype": "RichText/Contacts",
            "contenttype": "text",
            "content": """<contacts><c t="s" s="{0}" f="{1}"/></contacts>""".format(contact.id, contact.name)
        }
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, json=msg)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        return SkypeContactMsg(self.skype, id=msg["clientmessageid"], type=msg["messagetype"],
                               time=timeStr, userId=self.skype.user.id, chatId=self.id,
                               content=msg["content"], contactId=contact.id, contactName="{0}".format(contact.name))
    def delete(self):
        """
        Delete the conversation and all message history.
        """
        self.skype.conn("DELETE", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken)

@initAttrs
@convertIds("user", "users")
class SkypeSingleChat(SkypeChat):
    """
    A one-to-one conversation within Skype.

    Attributes:
        user (:class:`.SkypeUser`):
            The other participant in the conversation.
    """
    attrs = SkypeChat.attrs + ("userId",)
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeSingleChat, cls).rawToFields(raw)
        fields["userId"] = noPrefix(fields.get("id"))
        return fields
    @property
    def userIds(self):
        # Provided for convenience, so single and group chats both have a users field.
        return [self.userId]

@initAttrs
@convertIds("users", user=("creator",), users=("admin",))
class SkypeGroupChat(SkypeChat):
    """
    A group conversation within Skype.  Compared to single chats, groups have a topic and participant list.

    Attributes:
        topic (str):
            Description of the conversation, shown to all participants.
        creator (:class:`.SkypeUser`):
            User who originally created the conversation.
        users (:class:`.SkypeUser` list):
            Users currently participating in the conversation.
        admins (:class:`.SkypeUser` list):
            Participants with admin privileges.
        open (boolean):
            Whether new participants can join via a public join link.
        history (boolean):
            Whether message history is provided to new participants.
        picture (str):
            URL to retrieve the conversation picture.
        joinUrl (str):
            Public ``join.skype.com`` URL for any other users to access the conversation.
    """
    attrs = SkypeChat.attrs + ("topic", "creatorId", "userIds", "adminIds", "open", "history", "picture")
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeGroupChat, cls).rawToFields(raw)
        props = raw.get("properties", {})
        userIds = []
        adminIds = []
        for obj in raw.get("members", []):
            id = noPrefix(obj.get("id"))
            userIds.append(id)
            if obj.get("role") == "Admin":
                adminIds.append(id)
        fields.update({
            "topic": raw.get("threadProperties", {}).get("topic"),
            "creatorId": noPrefix(props.get("creator")),
            "userIds": userIds,
            "adminIds": adminIds,
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
                               auth=SkypeConnection.Auth.SkypeToken, json=query).json()["JoinUrl"]
    def setTopic(self, topic):
        """
        Update the topic message.  An empty string clears the topic.

        Args:
            topic (str): new conversation topic
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "topic"}, json={"topic": topic})
        self.topic = topic
    def setOpen(self, open):
        """
        Enable or disable joining by URL.  This does not affect current participants inviting others.

        Args:
            topic (str): whether to accept new participants via a public join link
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "joiningenabled"},
                        json={"joiningenabled": open})
        self.open = open
    def setHistory(self, history):
        """
        Enable or disable conversation history.  This only affects messages sent after the change.

        If disabled, new participants will not see messages before they arrived.

        Args:
            history (bool): whether to provide message history to new participants
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "historydisclosed"},
                        json={"historydisclosed": history})
        self.history = history
    def addMember(self, id, admin=False):
        """
        Add a user to the conversation, or update their user/admin status.

        Args:
            id (str): user identifier to invite
            admin (bool): whether the user will gain admin privileges
        """
        self.skype.conn("PUT", "{0}/threads/{1}/members/8:{2}".format(self.skype.conn.msgsHost, self.id, id),
                        auth=SkypeConnection.Auth.RegToken, json={"role": "Admin" if admin else "User"})
        if id not in self.userIds:
            self.userIds.append(id)
        if admin and id not in self.adminIds:
            self.adminIds.append(id)
        elif not admin and id in self.adminIds:
            self.adminIds.remove(id)
    def removeMember(self, id):
        """
        Remove a user from the conversation.

        Args:
            id (str): user identifier to remove
        """
        self.skype.conn("DELETE", "{0}/threads/{1}/members/8:{2}".format(self.skype.conn.msgsHost, self.id, id),
                        auth=SkypeConnection.Auth.RegToken)
        if id in self.userIds:
            self.userIds.remove(id)
    def leave(self):
        """
        Leave the conversation.  You will lose any admin rights.

        If public joining is disabled, you may need to be re-invited in order to return.
        """
        self.removeMember(self.skype.userId)

class SkypeChats(SkypeObjs):
    """
    A container of conversations, providing caching of user info to reduce API requests.

    Key lookups allow retrieving conversations by identifier.
    """
    def __getitem__(self, key):
        try:
            return super(SkypeChats, self).__getitem__(key)
        except KeyError:
            return self.chat(key)
    @syncState
    def recent(self):
        """
        Retrieve a selection of conversations with the most recent activity, and store them in the cache.

        Each conversation is only retrieved once, so subsequent calls will retrieve older conversations.

        Returns:
            :class:`SkypeChat` list: collection of recent conversations
        """
        url = "{0}/users/ME/conversations".format(self.skype.conn.msgsHost)
        params = {
            "startTime": 0,
            "view": "msnp24Equivalent",
            "targetType": "Passport|Skype|Lync|Thread"
        }
        def fetch(url, params):
            resp = self.skype.conn("GET", url, auth=SkypeConnection.Auth.RegToken, params=params).json()
            return resp, resp.get("_metadata", {}).get("syncState")
        def process(resp):
            chats = {}
            for json in resp.get("conversations", []):
                cls = SkypeSingleChat
                if "threadProperties" in json:
                    info = self.skype.conn("GET", "{0}/threads/{1}".format(self.skype.conn.msgsHost, json.get("id")),
                                           auth=SkypeConnection.Auth.RegToken,
                                           params={"view": "msnp24Equivalent"}).json()
                    json.update(info)
                    cls = SkypeGroupChat
                chats[json.get("id")] = self.merge(cls.fromRaw(self.skype, json))
            return chats
        return url, params, fetch, process
    def chat(self, id):
        """
        Get a single conversation by identifier.

        Args:
            id (str): user identifier to retrieve chat for
        """
        json = self.skype.conn("GET", "{0}/users/ME/conversations/{1}".format(self.skype.conn.msgsHost, id),
                               auth=SkypeConnection.Auth.RegToken, params={"view": "msnp24Equivalent"}).json()
        cls = SkypeSingleChat
        if "threadProperties" in json:
            info = self.skype.conn("GET", "{0}/threads/{1}".format(self.skype.conn.msgsHost, json.get("id")),
                                   auth=SkypeConnection.Auth.RegToken, params={"view": "msnp24Equivalent"}).json()
            json.update(info)
            cls = SkypeGroupChat
        return self.merge(cls.fromRaw(self.skype, json))
    def create(self, members=(), admins=()):
        """
        Create a new group chat with the given users.

        The current user is automatically added to the conversation as an admin.  Any other admin identifiers must also
        be present in the member list.

        Args:
            members (str list): user identifiers to initially join the conversation
            admins (str list): user identifiers to gain admin privileges
        """
        memberObjs = [{
            "id": "8:{0}".format(self.skype.userId),
            "role": "Admin"
        }]
        for id in members:
            if id == self.skype.userId:
                continue
            memberObjs.append({
                "id": "8:{0}".format(id),
                "role": "Admin" if id in admins else "User"
            })
        resp = self.skype.conn("POST", "{0}/threads".format(self.skype.conn.msgsHost),
                               auth=SkypeConnection.Auth.RegToken, json={"members": memberObjs})
        return self.chat(resp.headers["Location"].rsplit("/", 1)[1])
