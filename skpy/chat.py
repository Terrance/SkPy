from datetime import datetime
import re
import time

from .core import SkypeObj, SkypeObjs, SkypeApiException
from .util import SkypeUtils
from .conn import SkypeConnection
from .msg import SkypeMsg


@SkypeUtils.initAttrs
class SkypeChat(SkypeObj):
    """
    A conversation within Skype.

    Attributes:
        id (str):
            Unique identifier of the conversation.

            One-to-one chats have identifiers of the form ``<type>:<username>``.

            Cloud group chat identifiers are of the form ``<type>:<identifier>@thread.skype``.
    """

    attrs = ("id", "alerts")

    @classmethod
    def rawToFields(cls, raw={}):
        return {"id": raw.get("id"),
                "alerts": False if raw.get("properties", {}).get("alerts") == "false" else True}

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        id = raw.get("id")
        if "threadProperties" in raw:
            active = True
            try:
                info = skype.conn("GET", "{0}/threads/{1}".format(skype.conn.msgsHost, raw.get("id")),
                                  auth=SkypeConnection.Auth.RegToken,
                                  params={"view": "msnp24Equivalent"}).json()
            except SkypeApiException as e:
                if e.args[1].status_code in (403, 404):
                    active = False
                else:
                    raise
            else:
                raw.update(info)
            return SkypeGroupChat(skype, raw, **SkypeGroupChat.rawToFields(raw, active=active))
        else:
            return SkypeSingleChat(skype, raw, **SkypeSingleChat.rawToFields(raw))

    def getMsgs(self):
        """
        Retrieve a batch of messages from the conversation.

        This method can be called repeatedly to retrieve older messages.

        If new messages arrive in the meantime, they are returned first in the next batch.

        Returns:
            :class:`.SkypeMsg` list: collection of messages
        """
        url = "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id)
        params = {"startTime": 0,
                  "view": "supportsExtendedHistory|msnp24Equivalent|supportsMessageProperties",
                  "pageSize": 30}
        headers = {"BehaviorOverride": "redirectAs404",
                   "Sec-Fetch-Dest": "empty",
                   "Sec-Fetch-Mode": "cors",
                   "Sec-Fetch-Site": "cross-site"}
        resp = self.skype.conn.syncStateCall("GET", url, params, auth=SkypeConnection.Auth.RegToken, headers=headers).json()
        return [SkypeMsg.fromRaw(self.skype, json) for json in resp.get("messages", [])]

    def createRaw(self, msg):
        # All fields except timezone are required; 1418 = desktop client.
        client = ("os=Windows; osVer=10; proc=x86; lcid=en-US; deviceType=1; country=US; "
                  "clientName=skype4life; clientVer={0}//skype4life").format(SkypeConnection.SKYPE_CLIENT)
        resp = self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages"
                                       .format(self.skype.conn.msgsHost, self.id),
                               auth=SkypeConnection.Auth.RegToken, headers={"ClientInfo": client}, json=msg)
        url = resp.headers.get("Location")
        msgId = url.rsplit("/", 1)[-1] if url else None
        arriveTime = resp.json().get("OriginalArrivalTime")
        return (msgId, arriveTime)

    def editRaw(self, msgId, msg):
        resp = self.skype.conn("PUT", "{0}/users/ME/conversations/{1}/messages/{2}"
                                      .format(self.skype.conn.msgsHost, self.id, msgId),
                               auth=SkypeConnection.Auth.RegToken, json=msg)
        json = resp.json()
        if "errorCode" in json:
            raise SkypeApiException("Error code {0} from message edit".format(json["errorCode"]), resp)
        else:
            return json.get("edittime")

    def deleteRaw(self, msgId):
        resp = self.skype.conn("DELETE", "{0}/users/ME/conversations/{1}/messages/{2}"
                                         .format(self.skype.conn.msgsHost, self.id, msgId),
                               auth=SkypeConnection.Auth.RegToken)
        json = resp.json()
        if "errorCode" in json:
            raise SkypeApiException("Error code {0} from message delete".format(json["errorCode"]), resp)
        else:
            return json.get("deletetime")

    def sendRaw(self, editId=None, **kwargs):
        """
        Send a raw message to the conversation.  At a minimum, values for ``content``, ``messagetype`` and
        ``contenttype`` should be provided.

        The message object returned here will not have a server-provided identifier (needed for acks), as the messages
        API does not provide it.  Note that message edits depend on the client identifier, which is included.

        There is no need to include ``clientmessageid`` or ``skypeeditedid`` -- instead, use ``editId`` to update an
        existing message, otherwise a new one will be created with its own client identifier.

        Args:
            editId (int): identifier of an existing message to replace
            content (str): plain or HTML body for the message
            contenttype (str): format of the message, normally ``text``
            messagetype (str): base message type
            skypeemoteoffset (int): used with action messages to control where the user's name ends
            Has-Mentions (str): whether the message mentions any other users
            kwargs (dict): any additional arguments not listed above

        Returns:
            .SkypeMsg: copy of the sent message object
        """
        msg = {"contenttype": "text", "messagetype": "Text"}
        msg.update(kwargs)
        if editId:
            msgId = editId
            clientTime = None
            if msg.get("content"):
                arriveTime = self.editRaw(editId, msg)
            else:
                arriveTime = self.deleteRaw(editId)
        else:
            # Skype timestamps are integers and in milliseconds, whereas Python's are floats and in seconds.
            clientTime = int(time.time() * 1000)
            msg["clientmessageid"] = str(clientTime)
            msgId, arriveTime = self.createRaw(msg)
        arriveDate = datetime.fromtimestamp(arriveTime / 1000) if arriveTime else datetime.now()
        msg.update({"id": msgId,
                    "conversationLink": "{0}/users/ME/conversations/{1}".format(self.skype.conn.msgsHost, self.id),
                    "from": "{0}/users/ME/contacts/8:{1}".format(self.skype.conn.msgsHost, self.skype.userId),
                    "imdisplayname": str(self.skype.user.name),
                    "isactive": True,
                    "originalarrivaltime": datetime.strftime(arriveDate, "%Y-%m-%dT%H:%M:%S.%fZ"),
                    "type": "Message"})
        if clientTime:
            clientDate = datetime.fromtimestamp(clientTime / 1000)
            msg["composetime"] = datetime.strftime(clientDate, "%Y-%m-%dT%H:%M:%S.%fZ")
        if arriveTime:
            arriveDate = datetime.fromtimestamp(arriveTime / 1000)
            msg["originalarrivaltime"] = datetime.strftime(arriveDate, "%Y-%m-%dT%H:%M:%S.%fZ")
        return SkypeMsg.fromRaw(self.skype, msg)

    def setTyping(self, active=True):
        """
        Send a typing presence notification to the conversation.  This will typically show the "*<name> is typing...*"
        message in others clients.

        .. note:: A user's event stream will not receive any events for their own typing notifications.

        It may be necessary to send this type of message continuously, as each typing presence usually expires after a
        few seconds.  Set ``active`` to ``False`` to clear a current presence.

        Args:
            active (bool): whether to show as currently typing

        Returns:
            .SkypeMsg: copy of the sent message object
        """
        return self.sendRaw(messagetype="Control/{0}Typing".format("" if active else "Clear"), content=None)

    def sendMsg(self, content, me=False, rich=False, edit=None):
        """
        Send a text message to the conversation.

        If ``me`` is specified, the message is sent as an action (equivalent to ``/me <content>`` in other clients).
        This is typically displayed as "*<name>* ``<content>``", where clicking the name links back to your profile.

        Rich text can also be sent, provided it is formatted using Skype's subset of HTML.  Helper methods on the
        :class:`.SkypeMsg` class can generate the necessary markup.

        Args:
            content (str): main message body
            me (bool): whether to send as an action, where the current account's name prefixes the message
            rich (bool): whether to send with rich text formatting
            edit (int): client identifier of an existing message to edit

        Returns:
            .SkypeMsg: copy of the sent message object
        """
        msgType = "Text"
        kwargs = {"Has-Mentions": "false"}
        if me:
            content = "{0} {1}".format(self.skype.user.name, content)
            kwargs["skypeemoteoffset"] = len(str(self.skype.user.name)) + 1
        elif rich:
            msgType = "RichText"
            if re.search(r"""<at id=".+?">.+</at>""", content):
                kwargs["Has-Mentions"] = "true"
        return self.sendRaw(editId=edit, messagetype=msgType, content=content,
                            imdisplayname="{0}".format(self.skype.user.name), **kwargs)

    def sendFile(self, content, name, image=False):
        """
        Upload a file to the conversation.  Content should be an ASCII or binary file-like object.

        If an image, Skype will generate a thumbnail and link to the full image.

        Args:
            content (file): file-like object to retrieve the attachment's body
            name (str): filename displayed to other clients
            image (bool): whether to treat the file as an image

        Returns:
            .SkypeFileMsg: copy of the sent message object
        """
        meta = {"type": "pish/image" if image else "sharing/file",
                "permissions": dict(("8:{0}".format(id), ["read"]) for id in self.userIds)}
        if not image:
            meta["filename"] = name
        objId = self.skype.conn("POST", "https://api.asm.skype.com/v1/objects",
                                auth=SkypeConnection.Auth.Authorize,
                                headers={"X-Client-Version": "0/0.0.0.0"},
                                json=meta).json()["id"]
        objType = "imgpsh" if image else "original"
        urlFull = "https://api.asm.skype.com/v1/objects/{0}".format(objId)
        self.skype.conn("PUT", "{0}/content/{1}".format(urlFull, objType),
                        auth=SkypeConnection.Auth.Authorize, data=content.read())
        size = content.tell()
        if image:
            viewLink = SkypeMsg.link("https://api.asm.skype.com/s/i?{0}".format(objId))
            body = SkypeMsg.uriObject("""{0}<meta type="photo" originalName="{1}"/>""".format(viewLink, name),
                                      "Picture.1", urlFull, thumb="{0}/views/imgt1".format(urlFull), OriginalName=name)
        else:
            viewLink = SkypeMsg.link("https://login.skype.com/login/sso?go=webclient.xmm&docid={0}".format(objId))
            body = SkypeMsg.uriObject(viewLink, "File.1", urlFull, "{0}/views/thumbnail".format(urlFull), name, name,
                                      OriginalName=name, FileSize=size)
        msgType = "RichText/{0}".format("UriObject" if image else "Media_GenericFile")
        return self.sendRaw(content=body, messagetype=msgType)

    def sendContacts(self, *contacts):
        """
        Share one or more contacts with the conversation.

        Args:
            contacts (SkypeUser list): users to embed in the message

        Returns:
            .SkypeContactMsg: copy of the sent message object
        """
        contactTags = ("""<c t="s" s="{0}" f="{1}"/>""".format(contact.id, contact.name) for contact in contacts)
        content = """<contacts>{0}</contacts>""".format("".join(contactTags))
        return self.sendRaw(content=content, messagetype="RichText/Contacts")

    def setConsumption(self, horizon):
        """
        Update the user's consumption horizon for this conversation, i.e. where it has been read up to.

        To consume up to a given message, call :meth:`.SkypeMsg.read` instead.

        Args:
            horizon (str): new horizon string, of the form ``<id>,<timestamp>,<id>``
        """
        self.skype.conn("PUT", "{0}/users/ME/conversations/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "consumptionhorizon"},
                        json={"consumptionhorizon": horizon})

    def setAlerts(self, alerts):
        """
        Enable or disable message and event alerts for this conversation.

        Args:
            alerts (bool): whether to receive notifications
        """
        self.skype.conn("PUT", "{0}/users/ME/conversations/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "alerts"},
                        json={"alerts": str(alerts).lower()})
        self.alerts = alerts

    def delete(self):
        """
        Delete the conversation and all message history.
        """
        self.skype.conn("DELETE", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken)


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("user", "users")
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
        fields["userId"] = SkypeUtils.noPrefix(fields.get("id"))
        return fields

    @property
    def userIds(self):
        # Provided for convenience, so single and group chats both have a users field.
        return [self.userId]


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("users", user=("creator",), users=("admin",))
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
        open (bool):
            Whether new participants can join via a public join link.
        history (bool):
            Whether message history is provided to new participants.
        picture (str):
            URL to retrieve the conversation picture.
        joinUrl (str):
            Public ``join.skype.com`` URL for any other users to access the conversation.
        active (bool):
            Whether the full group chat was retrieved from the server.  This may be ``False`` if a group conversation
            still appears in the recent list despite being left or deleted.
        moderated (bool):
            Whether the group chat is a Skype Moderated Group.
    """

    attrs = SkypeChat.attrs + ("topic", "creatorId", "userIds", "adminIds", "open", "history", "picture", "active",
                               "moderated")

    @classmethod
    def rawToFields(cls, raw={}, active=False):
        fields = super(SkypeGroupChat, cls).rawToFields(raw)
        props = raw.get("properties", {})
        userIds = []
        adminIds = []
        for obj in raw.get("members", []):
            id = SkypeUtils.noPrefix(obj.get("id"))
            userIds.append(id)
            if obj.get("role") == "Admin":
                adminIds.append(id)
        fields.update({"topic": raw.get("threadProperties", {}).get("topic"),
                       "creatorId": SkypeUtils.noPrefix(props.get("creator")),
                       "userIds": userIds,
                       "adminIds": adminIds,
                       "moderated": props.get("moderatedthread") == "true",
                       "open": props.get("joiningenabled", "") == "true",
                       "history": props.get("historydisclosed", "") == "true",
                       "picture": props.get("picture", "")[4:] or None,
                       "active": active})
        return fields

    @property
    @SkypeUtils.cacheResult
    def joinUrl(self):
        return self.skype.conn("POST", "{0}/meetings".format(SkypeConnection.API_JOIN_CREATE),
                               auth=SkypeConnection.Auth.SkypeToken,
                               json={"threadId": self.id}).json().get("url")

    def setTopic(self, topic):
        """
        Update the topic message.  An empty string clears the topic.

        Args:
            topic (str): new conversation topic
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "topic"}, json={"topic": topic})
        self.topic = topic

    def setModerated(self, moderated=True):
        """
        Update the chat type, and make chat moderated.

        Args:
            moderated (bool): whether to enable moderation restrictions
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "moderatedthread"},
                        json={"moderatedthread": moderated})
        self.moderated = moderated

    def setOpen(self, open):
        """
        Enable or disable joining by URL.  This does not affect current participants inviting others.

        Args:
            open (bool): whether to accept new participants via a public join link
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

    def recent(self):
        """
        Retrieve a selection of conversations with the most recent activity, and store them in the cache.

        Each conversation is only retrieved once, so subsequent calls will retrieve older conversations.

        Returns:
            :class:`SkypeChat` dict: collection of recent conversations keyed by their ID
        """
        url = "{0}/users/ME/conversations".format(self.skype.conn.msgsHost)
        params = {"startTime": 0,
                  "view": "supportsExtendedHistory|msnp24Equivalent",
                  "targetType": "Passport|Skype|Lync|Thread|Agent|ShortCircuit|PSTN|Flxt|NotificationStream|"
                                "ModernBots|secureThreads|InviteFree"}
        resp = self.skype.conn.syncStateCall("GET", url, params, auth=SkypeConnection.Auth.RegToken).json()
        chats = {}
        for json in resp.get("conversations", []):
            chat = SkypeChat.fromRaw(self.skype, json)
            chats[chat.id] = self.merge(chat)
        return chats

    def chat(self, id):
        """
        Get a single conversation by identifier.

        Args:
            id (str): single or group chat identifier

        Returns:
            :class:`SkypeChat`: retrieved conversation
        """
        json = self.skype.conn("GET", "{0}/users/ME/conversations/{1}".format(self.skype.conn.msgsHost, id),
                               auth=SkypeConnection.Auth.RegToken, params={"view": "msnp24Equivalent"}).json()
        return self.merge(SkypeChat.fromRaw(self.skype, json))

    def create(self, members=(), admins=(), moderated=False):
        """
        Create a new group chat with the given users.

        The current user is automatically added to the conversation as an admin.  Any other admin identifiers must also
        be present in the member list.

        Args:
            members (str list): user identifiers to initially join the conversation
            admins (str list): user identifiers to gain admin privileges
            moderate (bool): whether to enable moderation restrictions

        Returns:
            :class:`SkypeGroupChat`: newly created group conversation
        """
        memberObjs = [{"id": "8:{0}".format(self.skype.userId), "role": "Admin"}]
        props = {"moderatedthread": moderated}
        for id in members:
            if id == self.skype.userId:
                continue
            memberObjs.append({"id": "8:{0}".format(id), "role": "Admin" if id in admins else "User"})
        resp = self.skype.conn("POST", "{0}/threads".format(self.skype.conn.msgsHost),
                               auth=SkypeConnection.Auth.RegToken, json={"members": memberObjs, "properties": props})
        return self.chat(resp.headers["Location"].rsplit("/", 1)[1])

    @staticmethod
    @SkypeUtils.cacheResult
    def urlToIds(url):
        """
        Resolve a ``join.skype.com`` URL and returns various identifiers for the group conversation.

        Args:
            url (str): public join URL, or identifier from it

        Returns:
            dict: related conversation's identifiers -- keys: ``id``, ``long``, ``blob``
        """
        urlId = url.split("/")[-1]
        convUrl = "https://join.skype.com/api/v2/conversation/"
        json = SkypeConnection.externalCall("POST", convUrl, json={"shortId": urlId, "type": "wl"}).json()
        return {"id": json.get("Resource"),
                "long": json.get("Id"),
                "blob": json.get("ChatBlob")}
