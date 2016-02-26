from datetime import datetime

from .conn import SkypeConnection
from .msg import SkypeMsg
from .util import SkypeObj, noPrefix, userToId, chatToId, initAttrs, convertIds, cacheResult


@initAttrs
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
        return {
            "id": raw.get("id"),
            "type": raw.get("resourceType"),
            "time": evtTime
        }

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        res = raw.get("resource", {})
        resType = raw.get("resourceType")
        evtCls = {
            "UserPresence": SkypePresenceEvent,
            "EndpointPresence": SkypeEndpointEvent,
            "NewMessage": SkypeMessageEvent,
            "ConversationUpdate": SkypeChatUpdateEvent,
            "ThreadUpdate": SkypeChatMemberEvent
        }.get(resType, cls)
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


@initAttrs
@convertIds("user")
class SkypePresenceEvent(SkypeEvent):
    """
    An event for contacts changing status or presence.

    Attributes:
        user (:class:`.SkypeUser`):
            User whose presence changed.
        online (bool):
            Whether the user is now connected.
        status (str):
            Chosen availability status.
    """

    attrs = SkypeEvent.attrs + ("userId", "online", "status")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypePresenceEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({
            "userId": userToId(res.get("selfLink")),
            "online": res.get("availability") == "Online",
            "status": res.get("status")
        })
        return fields


@initAttrs
@convertIds("user")
class SkypeEndpointEvent(SkypeEvent):
    """
    An event for changes to individual contact endpoints.

    Attributes:
        user (:class:`.SkypeUser`):
            User whose endpoint emitted an event.
    """

    attrs = SkypeEvent.attrs + ("userId",)

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeEndpointEvent, cls).rawToFields(raw)
        fields["userId"] = userToId(raw.get("resource", {}).get("selfLink"))
        return fields


@initAttrs
@convertIds("user", "chat")
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
        fields.update({
            "userId": userToId(res.get("from", "")),
            "chatId": chatToId(res.get("conversationLink", "")),
            "active": (res.get("messagetype") == "Control/Typing")
        })
        return fields


@initAttrs
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
    @cacheResult
    def msg(self):
        return SkypeMsg.fromRaw(self.skype, self.raw.get("resource", {}))


@initAttrs
class SkypeNewMessageEvent(SkypeMessageEvent):
    """
    An event for a new message being received in a conversation.
    """


@initAttrs
class SkypeEditMessageEvent(SkypeMessageEvent):
    """
    An event for the update of an existing message in a conversation.
    """


@initAttrs
class SkypeCallEvent(SkypeMessageEvent):
    """
    An event for incoming or missed Skype calls.
    """


@initAttrs
@convertIds("chat")
class SkypeChatUpdateEvent(SkypeEvent):
    """
    An event triggered by various conversation changes or messages.

    Attributes:
        chat (:class:`.SkypeChat`):
            Conversation that emitted an update.
        horizon (str):
            Raw list of timestamps, as provided by the API.
    """

    attrs = SkypeEvent.attrs + ("chatId", "horizon")

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeChatUpdateEvent, cls).rawToFields(raw)
        res = raw.get("resource", {})
        fields.update({
            "chatId": res.get("id"),
            "horizon": res.get("properties", {}).get("consumptionhorizon")
        })
        return fields

    def consume(self):
        """
        Use the consumption horizon to mark the conversation as up-to-date.
        """
        self.skype.conn("PUT", "{0}/users/ME/conversations/{1}/properties"
                               .format(self.skype.conn.msgsHost, self.chatId),
                        auth=SkypeConnection.Auth.RegToken, params={"name": "consumptionhorizon"},
                        json={"consumptionhorizon": self.horizon})


@initAttrs
@convertIds("users", "chat")
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
        fields.update({
            "userIds": filter(None, [noPrefix(m.get("id")) for m in res.get("members")]),
            "chatId": res.get("id")
        })
        return fields
