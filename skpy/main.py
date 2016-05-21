import requests

from .core import SkypeObj
from .util import SkypeUtils
from .conn import SkypeConnection
from .user import SkypeContact, SkypeContacts
from .chat import SkypeChats
from .event import SkypeEvent


class Skype(SkypeObj):
    """
    The main Skype instance.  Provides methods for retrieving various other object types.

    Attributes:
        user (:class:`.SkypeContact`):
            Contact information for the connected account.
        contacts (:class:`.SkypeContacts`):
            Container of contacts for the connected user.
        chats (:class:`.SkypeChats`):
            Container of conversations for the connected user.
        settings (:class:`.SkypeSettings`):
            Read/write access to server-side account options.
        services (dict):
            Skype credit and other paid services for the connected account.
        translate (:class:`.SkypeTranslator`):
            Connected instance of the translator service.
        conn (:class:`.SkypeConnection`):
            Underlying connection instance.
    """

    attrs = ("userId",)

    def __init__(self, user=None, pwd=None, tokenFile=None, connect=None):
        """
        Create a new Skype object and corresponding connection.

        If ``user`` and ``pwd`` are given, they will be passed to :meth:`.SkypeConnection.setUserPwd`.  If a token file
        path is present, it will be used if valid.  On a successful connection, the token file will also be written to.

        By default, a connection attempt will be made if any of ``user``, ``pwd`` or ``tokenFile`` are specified.  It
        is also possible to handle authentication manually, by working with the underlying connection object instead.

        Args:
            user (str): username of the connecting account
            pwd (str): password of the connecting account
            tokenFile (str): path to file used for token storage
            connect (bool): whether to try and connect straight away
        """
        super(Skype, self).__init__(self)
        self.conn = SkypeConnection()
        if tokenFile:
            self.conn.setTokenFile(tokenFile)
        if user and pwd:
            self.conn.setUserPwd(user, pwd)
        if connect is None:
            connect = (user and pwd) or tokenFile
        if connect:
            try:
                self.conn.readToken()
            except:
                self.conn.getSkypeToken()
        self.contacts = SkypeContacts(self)
        self.chats = SkypeChats(self)
        self.settings = SkypeSettings(self)
        self.translate = SkypeTranslator(self)

    @property
    def userId(self):
        return self.conn.userId

    @property
    @SkypeUtils.cacheResult
    def user(self):
        json = self.conn("GET", "{0}/users/self/profile".format(SkypeConnection.API_USER),
                         auth=SkypeConnection.Auth.SkypeToken).json()
        return SkypeContact.fromRaw(self, json)

    @property
    @SkypeUtils.cacheResult
    def services(self):
        return self.conn("GET", "{0}/users/{1}/services".format(SkypeConnection.API_ENTITLEMENT, self.userId),
                         auth=SkypeConnection.Auth.SkypeToken, headers={"Accept": "application/json; ver=3.0"}).json()

    @SkypeConnection.handle(404, regToken=True)
    @SkypeConnection.handle(404, subscribe="self")
    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events occur, the API will block for up to 30 seconds, after which an empty list is returned.  As soon as
        an event is received in this time, it is returned immediately.

        Returns:
            :class:`.SkypeEvent` list: a list of events, possibly empty
        """
        events = []
        for json in self.conn.endpoints["self"].getEvents():
            events.append(SkypeEvent.fromRaw(self, json))
        return events

    def setPresence(self, status=SkypeUtils.Status.Online):
        """
        Set the current user's presence on the network.  Supports :attr:`.Status.Online`, :attr:`.Status.Busy` or
        :attr:`.Status.Hidden` (shown as :attr:`.Status.Offline` to others).

        Args:
            status (.Status): new availability to display to contacts
        """
        self.conn("PUT", "{0}/users/ME/presenceDocs/messagingService".format(self.conn.msgsHost),
                  auth=SkypeConnection.Auth.RegToken, json={"status": status.label})

    def setAvatar(self, image):
        """
        Update the profile picture for the current user.

        Args:
            image (file): a file-like object to read the image from
        """
        self.conn("PUT", "{0}/users/{1}/profile/avatar".format(SkypeConnection.API_USER, self.userId),
                  auth=SkypeConnection.Auth.SkypeToken, data=image.read())

    def getUrlMeta(self, url):
        """
        Retrieve various metadata associated with a URL, as seen by Skype.

        Args:
            url (str): address to ping for info

        Returns:
            dict: metadata for the website queried
        """
        return self.conn("GET", SkypeConnection.API_URL, params={"url": url},
                         auth=SkypeConnection.Auth.Authorize).json()


class SkypeEventLoop(Skype):
    """
    A skeleton class for producing event processing programs.

    Attributes:
        autoAck (bool):
            Whether to automatically acknowledge all incoming events.
    """

    def __init__(self, user=None, pwd=None, tokenFile=None, autoAck=True):
        """
        Create a new event loop and the underlying connection.

        The ``user``, ``pwd`` and ``tokenFile``  arguments are passed to the :class:`.SkypeConnection` instance.

        Args:
            user (str): the connecting user's username
            pwd (str): the connecting user's account password
            tokenFile (str): path to a file, used to cache session tokens
            autoAck (bool): whether to automatically acknowledge all incoming events
        """
        super(SkypeEventLoop, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck

    def loop(self):
        """
        Handle any incoming events, by calling out to :meth:`onEvent` for each one.  This method does not return.
        """
        while True:
            try:
                events = self.getEvents()
            except requests.ConnectionError:
                continue
            for event in events:
                self.onEvent(event)
                if self.autoAck:
                    event.ack()

    def onEvent(self, event):
        """
        Subclasses should implement this method to react to messages and status changes.

        Args:
            event (SkypeEvent): an incoming event
        """
        pass


class SkypeSettings(SkypeObj):
    """
    An interface for getting and setting server options for the connected account.

    All attributes are read/write, with values fetched on each access, and implicit server writes when changed.

    Attributes:
        webLinkPreviews (bool):
            Skype for Web: replace URLs in messages with rich previews.

            *Web link previews: Show me a preview of websites I send or receive on Skype.*
        youtubePlayer (bool):
            Skype for Web: replace YouTube URLs with an inline player.

            *YouTube player: Use YouTube player directly to preview videos I send or receive.*
        mentionNotifs (bool):
            Skype for Web: trigger notifications when mentioned in a message.

            *@mention notifications: Always notify me when someone mentions me on Skype. (@<username>)*
        imagePaste (bool):
            Skype for Web: support sending image files by pasting into a conversation input field.

            *Enable image paste: Enable pasting of images from clipboard directly into the chat.*
        shareTyping (bool):
            Skype for Web: send typing notifications to contacts when active in conversations.

            *Typing indicator: Show when I am typing.*
        callPrivacy (:class:`Privacy`):
            Who to accept incoming audio calls from.
        videoPrivacy (:class:`Privacy`):
            Who to accept incoming video and screen-share requests from.
    """

    attrs = ("webLinkPreviews", "youtubePlayer", "mentionNotifs", "imagePaste", "shareTyping",
             "callPrivacy", "videoPrivacy")

    class Privacy:
        """
        Enum: privacy option values for incoming audio and video calls.
        """
        Anyone = 0
        """
        Allow from all Skype users.
        """
        Contacts = 1
        """
        Only allow from Skype users on the connected account's contact list.
        """
        Nobody = 2
        """
        Deny from all Skype users.
        """

    @property
    def flags(self):
        # Retrieve a list of all enabled flags.
        return self.skype.conn("GET", SkypeConnection.API_FLAGS, auth=SkypeConnection.Auth.SkypeToken).json()

    def flagProp(id, invert=False):
        @property
        def flag(self):
            return (id in self.flags) ^ invert

        @flag.setter
        def flag(self, val):
            val = bool(val) ^ invert
            if not val == (id in self.flags):
                self.skype.conn("PUT" if val else "DELETE", "{0}/{1}".format(SkypeConnection.API_FLAGS, id),
                                auth=SkypeConnection.Auth.SkypeToken)
        return flag

    def optProp(id):
        @property
        def opt(self):
            json = self.skype.conn("GET", "{0}/users/{1}/options/{2}".format(SkypeConnection.API_USER,
                                                                             self.skype.userId, id),
                                   auth=SkypeConnection.Auth.SkypeToken).json()
            return json.get("optionInt", json.get("optionStr", json.get("optionBin")))

        @opt.setter
        def opt(self, val):
            self.skype.conn("POST", "{0}/users/{1}/options/{2}".format(SkypeConnection.API_USER,
                                                                       self.skype.userId, id),
                            auth=SkypeConnection.Auth.SkypeToken, data={"integerValue": val})
        return opt

    webLinkPreviews = flagProp(11, True)
    youtubePlayer = flagProp(12)
    mentionNotifs = flagProp(13, True)
    imagePaste = flagProp(14)
    shareTyping = flagProp(20, True)

    # Hidden options, which are abstracted below to avoid the flag nonsense.
    callPrivacyOpt = optProp("OPT_SKYPE_CALL_POLICY")
    videoPrivacyContacts = flagProp(15)
    videoPrivacyNobody = flagProp(16)

    @property
    def callPrivacy(self):
        # Behaviour here is consistent with Skype for Web (neither 0 nor 1 displays as contacts only).
        return self.Privacy.Anyone if self.callPrivacyOpt == 0 else self.Privacy.Contacts

    @callPrivacy.setter
    def callPrivacy(self, val):
        self.callPrivacyOpt = 0 if val == self.Privacy.Anyone else 2

    @property
    def videoPrivacy(self):
        if self.videoPrivacyNobody:
            return self.Privacy.Nobody
        elif self.videoPrivacyContacts:
            return self.Privacy.Contacts
        else:
            return self.Privacy.Anyone

    @videoPrivacy.setter
    def videoPrivacy(self, val):
        self.videoPrivacyContacts = (val == self.Privacy.Contacts)
        self.videoPrivacyNobody = (val == self.Privacy.Nobody)

    # Now make these static methods so they can be used outside of the class.
    flagProp = staticmethod(flagProp)
    optProp = staticmethod(optProp)


class SkypeTranslator(SkypeObj):
    """
    An interface to Skype's translation API.

    Attributes:
        languages (dict):
            Known languages supported by the translator.
    """

    @property
    @SkypeUtils.cacheResult
    def languages(self):
        return self.skype.conn("GET", "{0}/languages".format(SkypeConnection.API_TRANSLATE),
                               auth=SkypeConnection.Auth.SkypeToken).json().get("text")

    def __call__(self, text, toLang, fromLang=None):
        """
        Attempt translation of a string.  Supports automatic language detection if ``fromLang`` is not specified.

        Args:
            text (str): input text to be translated
            toLang (str): country code of output language
            fromLang (str): country code of input language
        """
        return self.skype.conn("GET", "{0}/skype/translate".format(SkypeConnection.API_TRANSLATE),
                               params={"from": fromLang or "", "to": toLang, "text": text},
                               auth=SkypeConnection.Auth.SkypeToken).json()
