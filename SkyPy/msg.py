import re
from datetime import datetime, date
import time

from bs4 import BeautifulSoup

from .conn import SkypeConnection
from .static import emoticons
from .util import SkypeObj, noPrefix, userToId, chatToId, initAttrs, convertIds, cacheResult

@initAttrs
@convertIds("user", "chat")
class SkypeMsg(SkypeObj):
    """
    A message either sent or received in a conversation.

    Edits are represented by a follow-up messages that reference the original by :attr:`editId`.

    Attributes:
        id (str):
            Identifier of the message, usually a timestamp.
        type (str):
            Raw message type, as specified by the Skype API.
        time (datetime.datetime):
            Original arrival time of the message.
        editId (str):
            Reference to an original message, that this message provides an edit to.
        user (:class:`.SkypeUser`):
            User that sent the message.
        chat (:class:`.SkypeChat`):
            Conversation where this message was received.
        content (str):
            Raw message content, as received from the API.
    """
    @staticmethod
    def bold(s):
        """
        Format text to be bold.

        Args:
            s (str): string to format

        Returns:
            str: formatted string
        """
        return """<b raw_pre="*" raw_post="*">{0}</b>""".format(s)
    @staticmethod
    def italic(s):
        """
        Format text to be italic.

        Args:
            s (str): string to format

        Returns:
            str: formatted string
        """
        return """<i raw_pre="_" raw_post="_">{0}</i>""".format(s)
    @staticmethod
    def strike(s):
        """
        Format text to be struck through.

        Args:
            s (str): string to format

        Returns:
            str: formatted string
        """
        return """<s raw_pre="~" raw_post="~">{0}</s>""".format(s)
    @staticmethod
    def mono(s):
        """
        Format text to be monospaced.

        Args:
            s (str): string to format

        Returns:
            str: formatted string
        """
        return """<pre raw_pre="{{code}}" raw_post="{{code}}">{0}</pre>""".format(s)
    @staticmethod
    def link(url, display=None):
        """
        Create a hyperlink.  If ``display`` is not specified, display the URL.

        .. note:: Anomalous API behaviour: official clients don't provide the ability to set display text.

        Args:
            url (str): full URL to link to
            display (str): custom label for the hyperlink

        Returns:
            str: tag to display a hyperlink
        """
        return """<a href="{0}">{1}</a>""".format(url, display or url)
    @staticmethod
    def emote(shortcut):
        """
        Display an emoticon.  This accepts any valid shortcut.

        Args:
            shortcut (str): emoticon shortcut

        Returns:
            str: tag to render the emoticon
        """
        for emote in emoticons:
            if shortcut == emote or shortcut in emoticons[emote]["shortcuts"]:
                name = emoticons[emote]["shortcuts"][0] if shortcut == emote else shortcut
                return """<ss type="{0}">{1}</ss>""".format(emote, name)
        # No match, return the input as-is.
        return shortcut
    @staticmethod
    def quote(user, chat, timestamp, content):
        """
        Display a message excerpt as a quote from another user.

        Skype for Web doesn't support native quotes, and instead displays the legacy quote text.  Supported desktop
        clients show a blockquote with the author's name and timestamp underneath.

        .. note:: Anomalous API behaviour: it is possible to fake the message content of a quote.

        Args:
            user (SkypeUser): user who is to be quoted saying the message
            chat (SkypeChat): conversation the quote was originally seen in
            timestamp (datetime.datetime): original arrival time of the quoted message
            content (str): excerpt of the original message to be quoted

        Returns:
            str: tag to display the excerpt as a quote
        """
        # Single conversations lose their prefix here.
        chatId = chat.id if chat.id.split(":")[0] == "19" else noPrefix(chat.id)
        # Legacy timestamp includes the date if the quote is not from today.
        unixTime = int(time.mktime(timestamp.timetuple()))
        legacyTime = timestamp.strftime("{0}%H:%M:%S".format("" if timestamp.date() == date.today() else "%d/%m/%Y "))
        return """<quote author="{0}" authorname="{1}" conversation="{2}" timestamp="{3}"><legacyquote>""" \
               """[{4}] {1}: </legacyquote>{5}<legacyquote>\n\n&lt;&lt;&lt; </legacyquote></quote>""" \
               .format(user.id, user.name, chatId, unixTime, legacyTime, content)
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

        Hyperlinks are replaced with their target, and message edit tags are stripped.

        With ``entities`` set, instead of stripping all tags altogether, the following replacements are made:

        ========================  =========================
        Rich text                 Plain text
        ========================  =========================
        ``<b>bold</b>``           ``*bold*``
        ``<i>italic</i>``         ``_italic_``
        ``<s>strikethrough</s>``  ``~strikethrough~``
        ``<pre>monospace</pre>``  ``{code}monospace{code}``
        ========================  =========================

        Args:
            entities (bool): whether to preserve formatting using the plain text equivalents
        """
        if self.type == "RichText":
            text = re.sub(r"<e.*?/>", "", self.content)
            text = re.sub(r"""<a.*?href="(.*?)">.*?</a>""", r"\1", text)
            text = re.sub(r"</?b.*?>", "*" if entities else "", text)
            text = re.sub(r"</?i.*?>", "_" if entities else "", text)
            text = re.sub(r"</?s.*?>", "~" if entities else "", text)
            text = re.sub(r"</?pre.*?>", "{code}" if entities else "", text)
            text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") \
                       .replace("&quot;", "\"").replace("&apos;", "'")
            return text
        else:
            # It's already plain, or it's something we can't handle.
            return self.content
    def edit(self, content, me=False, rich=False):
        """
        Send an edit of this message.  Arguments are passed to :meth:`.SkypeChat.sendMsg`.

        .. note:: Anomalous API behaviour: messages can be undeleted by editing their content to be non-empty.

        Args:
            content (str): main message body
            me (bool): whether to send as an action, where the current account's name prefixes the message
            rich (bool): whether to send with rich text formatting
        """
        self.chat.sendMsg(content, me, rich, self.editId or self.id)
    def delete(self):
        """
        Delete the message and remove it from the conversation.

        Equivalent to calling :meth:`edit` with an empty ``content`` string.
        """
        self.edit("")

@initAttrs
@convertIds(user=("contact",))
class SkypeContactMsg(SkypeMsg):
    """
    A message containing a shared contact.

    Attributes:
        contact (:class:`.SkypeUser`):
            User object embedded in the message.
        contactName (str):
            Name of the user, as seen by the sender of the message.
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

    Attributes:
        file (File):
            File object embedded in the message.
        fileContent (bytes):
            Raw content of the file.
    """
    @initAttrs
    class File(SkypeObj):
        """
        Details about a file contained within a message.
        """
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
        return self.skype.conn("GET", "{0}/views/imgpsh_fullsize".format(self.file.urlFull),
                               auth=SkypeConnection.Auth.Authorize).content

@initAttrs
class SkypeCallMsg(SkypeMsg):
    """
    A message representing a change in state to a voice or video call inside the conversation.

    Attributes:
        state (:class:`State`):
            New state of the call.
    """
    class State:
        """
        Enum: possible call states (either started and incoming, or ended).
        """
        Started = 0
        """
        The call has just begun.
        """
        Ended = 1
        """
        All call participants have hung up.
        """
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

    Note that Skype represents these messages as being sent *by the conversation*, rather than the initiator.  Instead,
    :attr:`user <SkypeMsg.user>` is set to the initiator, and :attr:`member` to the target.

    Attributes:
        member (:class:`.SkypeUser`):
            User being added to or removed from the conversation.
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
