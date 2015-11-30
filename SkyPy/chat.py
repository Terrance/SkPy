import re
import time
from datetime import datetime

from .conn import SkypeConnection
from .static import emoticons
from .util import SkypeObj, upper, noPrefix, userToId, chatToId, convertIds, initAttrs, cacheResult, syncState

@initAttrs
class SkypeUser(SkypeObj):
    """
    A user on Skype -- the current one, a contact, or someone else.

    Properties differ slightly between the current user and others.  Only public properties are available here.

    Searches different possible attributes for each property.  Also deconstructs a merged first name field.
    """
    @initAttrs
    class Name(SkypeObj):
        """
        The name of a user or contact.
        """
        attrs = ("first", "last")
        def __str__(self):
            return " ".join(filter(None, (self.first, self.last)))
    @initAttrs
    class Location(SkypeObj):
        """
        The location of a user or contact.
        """
        attrs = ("city", "region", "country")
        def __str__(self):
            return ", ".join(filter(None, (self.city, self.region, self.country)))
    @initAttrs
    class Mood(SkypeObj):
        """
        The mood message set by a user or contact.
        """
        attrs = ("plain", "rich")
        def __str__(self):
            return self.plain or ""
    attrs = ("id", "name", "location", "avatar", "mood")
    defaults = dict(name=Name(), location=Location())
    @classmethod
    def rawToFields(cls, raw={}):
        firstName = raw.get("firstname", raw.get("name", {}).get("first"))
        lastName = raw.get("lastname", raw.get("name", {}).get("surname"))
        # Some clients stores the whole name in the user's first name field.
        if not lastName and firstName and " " in firstName:
            firstName, lastName = firstName.rsplit(" ", 1)
        name = SkypeUser.Name(first=firstName, last=lastName)
        locationParts = raw.get("locations")[0] if "locations" in raw else {
            "city": raw.get("city"),
            "region": raw.get("province"),
            "country": raw.get("country")
        }
        location = SkypeUser.Location(city=locationParts.get("city"), region=locationParts.get("region"), country=upper(locationParts.get("country")))
        avatar = raw.get("avatar_url", raw.get("avatarUrl"))
        mood = SkypeUser.Mood(plain=raw.get("mood"), rich=raw.get("richMood")) if raw.get("mood") or raw.get("richMood") else None
        return {
            "id": raw.get("id", raw.get("username")),
            "name": name,
            "location": location,
            "avatar": avatar,
            "mood": mood
        }
    @property
    def chat(self):
        """
        Return the conversation object for this user.
        """
        return self.skype.getChat("8:" + self.id)
    def invite(self, greeting=None):
        """
        Send the user a contact request.
        """
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}".format(SkypeConnection.API_USER, self.id), json={"greeting": greeting})

@initAttrs
class SkypeContact(SkypeUser):
    """
    A user on Skype that the logged-in account is a contact of.  Allows access to contacts-only properties.
    """
    @initAttrs
    class Phone(SkypeObj):
        """
        The phone number of a contact.
        """
        class Type:
            """
            Enum: types of phone number.
            """
            Home, Work, Mobile = range(3)
        attrs = ("type", "number")
        def __str__(self):
            return self.number or ""
    attrs = SkypeUser.attrs + ("language", "phones", "birthday", "authorised", "blocked")
    defaults = dict(SkypeUser.defaults, phones=[])
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeContact, cls).rawToFields(raw)
        phonesMap = {
            "Home": SkypeContact.Phone.Type.Home,
            "Office": SkypeContact.Phone.Type.Work,
            "Mobile": SkypeContact.Phone.Type.Mobile
        }
        phonesParts = raw.get("phones", [])
        for k in phonesMap:
            if raw.get("phone" + k):
                phonesParts.append({
                    "type": phonesMap[k],
                    "number": raw.get("phone" + k)
                })
        phones = [SkypeContact.Phone(type=p["type"], number=p["number"]) for p in phonesParts]
        try:
            birthday = datetime.strptime(raw.get("birthday") or "", "%Y-%m-%d").date()
        except ValueError:
            birthday = None
        fields.update({
            "language": upper(raw.get("language")),
            "phones": phones,
            "birthday": birthday,
            "authorised": raw.get("authorized"),
            "blocked": raw.get("blocked")
        })
        return fields

@initAttrs
@convertIds("user")
class SkypeRequest(SkypeObj):
    """
    A contact request.  Use accept() or reject() to act on it.
    """
    attrs = ("userId", "greeting")
    @classmethod
    def rawToFields(cls, raw={}):
        return {
            "userId": raw.get("sender"),
            "greeting": raw.get("greeting")
        }
    def accept(self):
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/accept".format(SkypeConnection.API_USER, self.userId), auth=SkypeConnection.Auth.Skype).json()
    def reject(self):
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/decline".format(SkypeConnection.API_USER, self.userId), auth=SkypeConnection.Auth.Skype).json()

@initAttrs
class SkypeChat(SkypeObj):
    """
    A conversation within Skype.

    Can be either one-to-one (identifiers of the form <type>:<username>) or a cloud group (<type>:<identifier>@thread.skype).
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

        If edit is specified, perform an edit of the message with that identifier.
        """
        timeId = int(time.time())
        msgId = edit or timeId
        msgType = "RichText" if rich else "Text"
        msgRaw = {
            ("skypeeditedid" if edit else "cilientmessageid"): msgId,
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
        self.skype.conn("POST", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id), auth=SkypeConnection.Auth.Reg, json=msgRaw)
        timeStr = datetime.strftime(datetime.now(), "%Y-%m-%dT%H:%M:%S.%fZ")
        editId = msgId if edit else None
        return SkypeMsg(self.skype, id=timeId, type=msgType, time=timeStr, editId=editId, userId=self.skype.user.id, chatId=self.id, content=content)
    def delete(self):
        """
        Delete the conversation and all message history.
        """
        self.skype.conn("DELETE", "{0}/users/ME/conversations/{1}/messages".format(self.skype.conn.msgsHost, self.id), auth=SkypeConnection.Auth.Reg)

@initAttrs
@convertIds("user")
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

@initAttrs
@convertIds("creator", "users")
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
        return self.skype.conn("POST", "{0}/threads".format(SkypeConnection.API_SCHEDULE), auth=SkypeConnection.Auth.Skype, json={
            "baseDomain": "https://join.skype.com/launch/",
            "threadId": self.id
        }).json()["JoinUrl"]
    def setTopic(self, topic):
        """
        Update the topic message.  An empty string clears the topic.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id), auth=SkypeConnection.Auth.Reg, params={"name": "topic"}, json={"topic": topic})
        self.topic = topic
    def setOpen(self, open):
        """
        Enable or disable public join links.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id), auth=SkypeConnection.Auth.Reg, params={"name": "joiningenabled"}, json={"joiningenabled": open})
        self.open = open
    def setHistory(self, history):
        """
        Enable or disable conversation history.
        """
        self.skype.conn("PUT", "{0}/threads/{1}/properties".format(self.skype.conn.msgsHost, self.id), auth=SkypeConnection.Auth.Reg, params={"name": "historydisclosed"}, json={"historydisclosed": history})
        self.history = history
    def leave(self):
        """
        Leave the conversation.  You will lose any admin rights.

        If public joining is disabled, you may need to be re-invited in order to return.
        """
        self.skype.conn("DELETE", "{0}/threads/{1}/members/8:{2}".format(self.skype.conn.msgsHost, self.id, self.skype.userId), auth=SkypeConnection.Auth.Reg)

@initAttrs
@convertIds("user", "chat")
class SkypeMsg(SkypeObj):
    """
    A message either sent or received in a conversation.

    Edits are represented by the original message, followed by subsequent messages that reference the original by editId.
    """
    @staticmethod
    def bold(s):
        return '<b raw_pre="*" raw_post="*">{0}</b>'.format(s)
    @staticmethod
    def italic(s):
        return '<i raw_pre="_" raw_post="_">{0}</i>'.format(s)
    @staticmethod
    def monospace(s):
        return '<pre raw_pre="!! ">{0}</pre>'.format(s)
    @staticmethod
    def emote(s):
        for emote in emoticons:
            if s == emote or s in emoticons[emote]["shortcuts"]:
                return '<ss type="{0}">{1}</ss>'.format(emote, emoticons[emote]["shortcuts"][0] if s == emote else s)
        return s
    attrs = ("id", "type", "time", "editId", "userId", "chatId", "content")
    @classmethod
    def rawToFields(cls, raw={}):
        return {
            "id": raw.get("id"),
            "type": raw.get("messagetype"),
            "time": datetime.strptime(raw.get("originalarrivaltime"), "%Y-%m-%dT%H:%M:%S.%fZ") if raw.get("originalarrivaltime") else datetime.now(),
            "editId": raw.get("skypeeditedid"),
            "userId": userToId(raw.get("from", "")),
            "chatId": chatToId(raw.get("conversationLink", "")),
            "content": raw.get("content")
        }
