import re
from datetime import datetime

from bs4 import BeautifulSoup

from .conn import SkypeConnection
from .static import emoticons
from .util import SkypeObj, noPrefix, userToId, chatToId, initAttrs, convertIds, cacheResult

@initAttrs
@convertIds("user", "chat")
class SkypeMsg(SkypeObj):
    """
    A message either sent or received in a conversation.

    Edits are represented by a follow-up messages that reference the original by editId.
    """
    @staticmethod
    def bold(s):
        return """<b raw_pre="*" raw_post="*">{0}</b>""".format(s)
    @staticmethod
    def italic(s):
        return """<i raw_pre="_" raw_post="_">{0}</i>""".format(s)
    @staticmethod
    def strike(s):
        return """<s raw_pre="~" raw_post="~">{0}</s>""".format(s)
    @staticmethod
    def mono(s):
        return """<pre raw_pre="{{code}}" raw_post="{{code}}">{0}</pre>""".format(s)
    @staticmethod
    def link(l, s=None):
        return """<a href="{0}">{1}</a>""".format(l, s or l)
    @staticmethod
    def emote(s):
        for emote in emoticons:
            if s == emote or s in emoticons[emote]["shortcuts"]:
                name = emoticons[emote]["shortcuts"][0] if s == emote else s
                return """<ss type="{0}">{1}</ss>""".format(emote, name)
        return s
    attrs = ("id", "type", "time", "editId", "userId", "chatId", "content")
    @classmethod
    def rawToFields(cls, raw={}):
        try:
            msgTime = datetime.strptime(raw.get("originalarrivaltime", ""), "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            msgTime = datetime.now()
        return {
            "id": raw.get("id"),
            "type": raw.get("messagetype"),
            "time": msgTime,
            "editId": raw.get("skypeeditedid"),
            "userId": userToId(raw.get("from", "")),
            "chatId": chatToId(raw.get("conversationLink", "")),
            "content": raw.get("content")
        }
    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        """
        Return a subclass instance of SkypeMsg if appropriate.
        """
        msgCls = {
            "RichText/Contacts": SkypeContactMsg,
            "RichText/Media_GenericFile": SkypeFileMsg,
            "RichText/UriObject": SkypeImageMsg,
            "Event/Call": SkypeCallMsg,
            "ThreadActivity/AddMember": SkypeAddMemberMsg,
            "ThreadActivity/DeleteMember": SkypeRemoveMemberMsg
        }.get(raw.get("messagetype"), cls)
        return msgCls(skype, raw, **msgCls.rawToFields(raw))
    def plain(self, entities=False):
        """
        Attempt to convert the message to plain text.

        With entities, formatting is converted to plain equivalents (e.g. *bold*).
        """
        if self.type == "RichText":
            text = self.content.replace("&quot;", "\"")
            text = re.sub(r"<e.*?/>", "", text)
            text = re.sub(r"""<a.*?href="(.*?)">.*?</a>""", r"\1", text)
            text = re.sub(r"</?b.*?>", "*" if entities else "", text)
            text = re.sub(r"</?i.*?>", "_" if entities else "", text)
            text = re.sub(r"</?s.*?>", "~" if entities else "", text)
            text = re.sub(r"</?pre.*?>", "{code}" if entities else "", text)
            return text
        else:
            # It's already plain, or it's something we can't handle.
            return self.content
    def edit(self, content, me=False, rich=False):
        """
        Send an edit of this message.  Follows the same arguments as SkypeChat.sendMsg().
        """
        self.chat.sendMsg(content, me, rich, self.editId or self.id)
    def delete(self):
        """
        Delete the message and remove it from the conversation.  Equivalent to edit(content="").
        """
        self.edit("")

@initAttrs
@convertIds(user=("contact",))
class SkypeContactMsg(SkypeMsg):
    """
    A message containing a shared contact.
    """
    attrs = SkypeMsg.attrs + ("contactId", "contactName")
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeContactMsg, cls).rawToFields(raw)
        contact = BeautifulSoup(raw.get("content"), "html.parser").find("c")
        if contact:
            fields.update({
                "contactId": contact.get("s"),
                "contactName": contact.get("f")
            })
        return fields

@initAttrs
class SkypeFileMsg(SkypeMsg):
    """
    A message containing a file shared in a conversation.
    """
    @initAttrs
    class File(SkypeObj):
        attrs = ("name", "size", "urlFull", "urlThumb", "urlView")
    attrs = SkypeMsg.attrs + ("file",)
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeFileMsg, cls).rawToFields(raw)
        # BeautifulSoup converts tag names to lower case, and find() is case-sensitive.
        file = BeautifulSoup(raw.get("content"), "html.parser").find("uriobject")
        if file:
            fileFields = {
                "name": (file.find("originalname") or {}).get("v"),
                "size": (file.find("filesize") or {}).get("v"),
                "urlFull": file.get("uri"),
                "urlThumb": file.get("url_thumbnail"),
                "urlView": (file.find("a") or {}).get("href")
            }
            fields["file"] = SkypeFileMsg.File(**fileFields)
        return fields
    @property
    @cacheResult
    def fileContent(self):
        """
        Retrieve the contents of the file as a byte string.
        """
        return self.skype.conn("GET", "{0}/views/original".format(self.file.urlFull),
                               auth=SkypeConnection.Auth.Authorize).content

@initAttrs
class SkypeImageMsg(SkypeFileMsg):
    """
    A message containing a picture shared in a conversation.
    """
    @property
    @cacheResult
    def fileContent(self):
        """
        Retrieve the image as a byte string.
        """
        return self.skype.conn("GET", "{0}/views/imgpsh_fullsize".format(self.file.urlFull),
                               auth=SkypeConnection.Auth.Authorize).content

@initAttrs
class SkypeCallMsg(SkypeMsg):
    """
    A message representing a change in state to a call inside the conversation.
    """
    class State:
        """
        Enum: possible call states (either started and incoming, or ended).
        """
        Started, Ended = range(2)
    attrs = SkypeMsg.attrs + ("state",)
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeCallMsg, cls).rawToFields(raw)
        partType = (BeautifulSoup(raw.get("content"), "html.parser").find("partlist") or {}).get("type")
        fields["state"] = {"started": cls.State.Started, "ended": cls.State.Ended}[partType]
        return fields

@initAttrs
@convertIds(user=("member",))
class SkypeMemberMsg(SkypeMsg):
    """
    A message representing a change in a group conversation's participants.

    Note that Skype represents these messages as being sent by the conversation user, rather than the initiator.

    Instead, user is set to the initiator, and member to the target.
    """
    attrs = SkypeMsg.attrs + ("memberId",)

@initAttrs
class SkypeAddMemberMsg(SkypeMemberMsg):
    """
    A message representing a user added to a group conversation.
    """
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeAddMemberMsg, cls).rawToFields(raw)
        addInfo = (BeautifulSoup(raw.get("content"), "html.parser").find("addmember") or {})
        fields.update({
            "userId": noPrefix(addInfo.find("initiator").text),
            "memberId": noPrefix(addInfo.find("target").text)
        })
        return fields

@initAttrs
class SkypeRemoveMemberMsg(SkypeMemberMsg):
    """
    A message representing a user removed from a group conversation.
    """
    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeRemoveMemberMsg, cls).rawToFields(raw)
        addInfo = (BeautifulSoup(raw.get("content"), "html.parser").find("deletemember") or {})
        fields.update({
            "userId": noPrefix(addInfo.find("initiator").text),
            "memberId": noPrefix(addInfo.find("target").text)
        })
        return fields
