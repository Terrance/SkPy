from datetime import datetime

from .core import SkypeObj
from .util import SkypeUtils
from .conn import SkypeConnection
from .msg import SkypeMsg


@SkypeUtils.initAttrs
class SkypeEvent(SkypeObj):
    """
    The base Skype event.  Pulls out common identifier, time and type parameters.

    Attributes:
        id (int):
            Unique identifier of the event, usually starting from ``1000``.
        type (str):
            Raw message type, as specified by the Skype API.
        time (datetime.datetime):
            Time at which the event occurred.
    """

    attrs = ("id", "type", "time")

    @classmethod
    def rawToFields(cls, raw={}):
        try:
            evtTime = datetime.strptime(raw.get("time", ""), "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            evtTime = datetime.now()
        return {"id": raw.get("id"),
                "type": raw.get("resourceType"),
                "time": evtTime}

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        res = raw.get("resource", {})
        resType = raw.get("resourceType")
        evtCls = {"UserPresence": SkypePresenceEvent,
                  "EndpointPresence": SkypeEndpointEvent,
                  "NewMessage": SkypeMessageEvent,
                  "ConversationUpdate": SkypeChatUpdateEvent,
                  "ThreadUpdate": SkypeChatMemberEvent}.get(resType, cls)
        if evtCls is SkypeMessageEvent:
            msgType = res.get("messagetype")
            if msgType in ("Text", "RichText", "RichText/Contacts", "RichText/Media_GenericFile", "RichText/UriObject"):
                evtCls = SkypeEditMessageEvent if res.get("skypeeditedid") else SkypeNewMessageEvent
            elif msgType in ("Control/Typing", "Control/ClearTyping"):
                evtCls = SkypeTypingEvent
            elif msgType == "Event/Call":
                evtCls = SkypeCallEvent
        return evtCls(skype, raw, **evtCls.rawToFields(raw))

    def ack(self):
        """
        Acknowledge receipt of an event, if a response is required.
        """
        url = self.raw.get("resource", {}).get("ackrequired")
        if url:
            self.skype.conn("POST", url, auth=SkypeConnection.Auth.RegToken)


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("user")
class SkypePresenceEvent(SkypeEvent):
    """
    An event for contacts changing status or presence.

    Attributes:
        user (:class:`.SkypeUser`):
            User whose presence changed.
        online (bool):
            Whether the user is now connected.
        status (:class:`.Status`):
            Chosen availability status.
        capabilities (str list):
            Features currently available from this user, across all endpoints.
    """

    attrs = SkypeEvent.attrs + ("userId", "online", "status", "capabilities")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypePresenceEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({"userId": SkypeUtils.userToId(res.get("selfLink")),
                       "online": res.get("availability") == "Online",
                       "status": getattr(SkypeUtils.Status, res.get("status")),
                       "capabilities": list(filter(None, res.get("capabilities", "").split(" | ")))})
        return fields


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("user")
class SkypeEndpointEvent(SkypeEvent):
    """
    An event for changes to individual contact endpoints.

    Attributes:
        user (:class:`.SkypeUser`):
            User whose endpoint emitted an event.
        name (str):
            Name of the device connected with this endpoint.
        capabilities (str list):
            Features available on the device.
        type (str):
            Numeric type of client that the device identifies as.
        version (str):
            Software version of the client.
    """

    attrs = SkypeEvent.attrs + ("userId", "name", "capabilities", "type", "version")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeEndpointEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        public = res.get("publicInfo", {})
        fields.update({"userId": SkypeUtils.userToId(res.get("selfLink")),
                       "name": res.get("privateInfo", {}).get("epname"),
                       "capabilities": list(filter(None, public.get("capabilities", "").split(" | "))),
                       "type": public.get("typ"),
                       "version": public.get("skypeNameVersion")})
        return fields


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("user", "chat")
class SkypeTypingEvent(SkypeEvent):
    """
    An event for users starting or stopping typing in a conversation.

    Attributes:
        user (:class:`.SkypeUser`):
            User whose typing status changed.
        chat (:class:`.SkypeChat`):
            Conversation where the user was seen typing.
        active (bool):
            Whether the user has just started typing.
    """

    attrs = SkypeEvent.attrs + ("userId", "chatId", "active")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeTypingEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({"userId": SkypeUtils.userToId(res.get("from", "")),
                       "chatId": SkypeUtils.chatToId(res.get("conversationLink", "")),
                       "active": (res.get("messagetype") == "Control/Typing")})
        return fields


@SkypeUtils.initAttrs
class SkypeMessageEvent(SkypeEvent):
    """
    The base message event, when a message is received in a conversation.

    Attributes:
        msg (:class:`.SkypeMsg`):
            Message received in the conversation.
    """

    attrs = SkypeEvent.attrs + ("msgId",)

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeMessageEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields["msgId"] = int(res.get("id")) if "id" in res else None
        return fields

    @property
    @SkypeUtils.cacheResult
    def msg(self):
        return SkypeMsg.fromRaw(self.skype, self.raw.get("resource", {}))


@SkypeUtils.initAttrs
class SkypeNewMessageEvent(SkypeMessageEvent):
    """
    An event for a new message being received in a conversation.
    """


@SkypeUtils.initAttrs
class SkypeEditMessageEvent(SkypeMessageEvent):
    """
    An event for the update of an existing message in a conversation.
    """


@SkypeUtils.initAttrs
class SkypeCallEvent(SkypeMessageEvent):
    """
    An event for incoming or missed Skype calls.
    """


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("chat")
class SkypeChatUpdateEvent(SkypeEvent):
    """
    An event triggered by various conversation changes or messages.

    Attributes:
        chat (:class:`.SkypeChat`):
            Conversation that emitted an update.
        horizon (str):
            Updated horizon string, in the form ``<id>,<timestamp>,<id>``.
    """

    attrs = SkypeEvent.attrs + ("chatId", "horizon")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeChatUpdateEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({"chatId": res.get("id"),
                       "horizon": res.get("properties", {}).get("consumptionhorizon")})
        return fields

    def consume(self):
        """
        Use the consumption horizon to mark the conversation as up-to-date.
        """
        self.skype.conn("PUT", "{0}/users/ME/conversations/{1}/properties"
                               .format(self.skype.conn.msgsHost, self.chatId),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "consumptionhorizon"},
                        json={"consumptionhorizon": self.horizon})


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("users", "chat")
class SkypeChatMemberEvent(SkypeEvent):
    """
    An event triggered when someone is added to or removed from a conversation.

    Attributes:
        users (:class:`.SkypeUser` list):
            List of users affected by the update.
        chat (:class:`.SkypeChat`):
            Conversation where the change occurred.
    """

    attrs = SkypeEvent.attrs + ("userIds", "chatId")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeChatMemberEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({"userIds": filter(None, [SkypeUtils.noPrefix(m.get("id")) for m in res.get("members")]),
                       "chatId": res.get("id")})
        return fields
