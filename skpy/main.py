from uuid import uuid4

import requests

from .core import SkypeObj, SkypeEnum, SkypeAuthException
from .util import SkypeUtils
from .conn import SkypeConnection
from .user import SkypeUser, SkypeContact, SkypeContacts
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

    def __init__(self, user=None, pwd=None, tokenFile=None, connect=True):
        """
        Create a new Skype object and corresponding connection.

        If ``user`` and ``pwd`` are given, they will be passed to :meth:`.SkypeConnection.setUserPwd`.  This can be
        either a Skype username/password pair, or a Microsoft account email address and its associated password.

        If a token file path is present, it will be used if valid.  On a successful connection, the token file will
        also be written to.

        By default, a connection attempt will be made if any valid form of credentials are supplied.  It is also
        possible to handle authentication manually, by working with the underlying connection object instead.

        Args:
            user (str): Skype username of the connecting account
            pwd (str): corresponding Skype account password
            tokenFile (str): path to file used for token storage
            connect (bool): whether to try and connect straight away

        Raises:
            .SkypeAuthException: if connecting, and the login request is rejected
            .SkypeApiException: if connecting, and the login form can't be processed
        """
        super(Skype, self).__init__(self)
        self.conn = SkypeConnection()
        if tokenFile:
            self.conn.setTokenFile(tokenFile)
        if user and pwd:
            self.conn.setUserPwd(user, pwd)
        if connect and ((user and pwd) or tokenFile):
            try:
                self.conn.readToken()
            except SkypeAuthException:
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

    def subscribePresence(self):
        """
        Subscribe to contact presence events.
        """
        self.conn.endpoints["self"].subscribePresence(self.contacts)

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

    def setMood(self, mood):
        """
        Update the activity message for the current user.

        Args:
            mood (str): new mood message
        """
        self.conn("POST", "{0}/users/{1}/profile/partial".format(SkypeConnection.API_USER, self.userId),
                  auth=SkypeConnection.Auth.SkypeToken, json={"payload": {"mood": mood or ""}})
        self.user.mood = SkypeUser.Mood(plain=mood) if mood else None

    def setAvatar(self, image):
        """
        Update the profile picture for the current user.

        Args:
            image (file): a file-like object to read the image from
        """
        self.conn("PUT", "{0}/v1/avatars/{1}".format(SkypeConnection.API_AVATAR, self.userId),
                  auth=SkypeConnection.Auth.SkypeToken, data=image.read(), headers={"Content-Type": "image/jpeg"})

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
    A skeleton class for producing event processing programs.  Implementers will most likely want to override the
    :meth:`onEvent` method.

    Attributes:
        autoAck (bool):
            Whether to automatically acknowledge all incoming events.
    """

    attrs = Skype.attrs + ("autoAck",)

    def __init__(self, user=None, pwd=None, tokenFile=None, autoAck=True, status=None):
        """
        Create a new event loop and the underlying connection.

        All arguments up to ``tokenFile``  are passed to the :class:`.SkypeConnection` instance.

        Args:
            user (str): Skype username of the connecting account
            pwd (str): corresponding Skype account password
            tokenFile (str): path to file used for token storage
            autoAck (bool): whether to automatically acknowledge all incoming events
            status (.Status): availability to display to contacts
        """
        super(SkypeEventLoop, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck
        if status:
            self.setPresence(status)

    def cycle(self):
        """
        Request one batch of events from Skype, calling :meth:`onEvent` with each event in turn.

        Subclasses may override this method to alter loop functionality.
        """
        try:
            events = self.getEvents()
        except requests.ConnectionError:
            return
        for event in events:
            self.onEvent(event)
            if self.autoAck:
                event.ack()

    def loop(self):
        """
        Continuously handle any incoming events using :meth:`cycle`.

        This method does not return, so for programs with a UI, this will likely need to be run in its own thread.
        """
        while True:
            self.cycle()

    def onEvent(self, event):
        """
        A stub method that subclasses should implement to react to messages and status changes.

        Args:
            event (SkypeEvent): an incoming event
        """
        pass


class SkypeSettings(SkypeObj):
    """
    An interface for getting and setting server options for the connected account.

    All attributes are read/write, with values fetched on each access, and implicit server writes when changed.

    Attributes:
        notificationPopups (bool):
            Skype for Web (Notifications): show browser notifications on new messages.
        notificationSounds (bool):
            Skype for Web (Sounds): play the Skype pop sound on new messages.
        webLinkPreviews (bool):
            Skype for Web (Web link previews): replace URLs in messages with rich previews.
        youtubePlayer (bool):
            Skype for Web (YouTube player): replace YouTube URLs with an inline player.
        mentionNotifs (bool):
            Skype for Web (@mention notifications): trigger notifications when mentioned in a message.
        imagePaste (bool):
            Skype for Web (Enable image paste): support sending image files by pasting into a conversation input field.
        shareTyping (bool):
            Skype for Web (Typing indicator): send typing notifications to contacts when active in conversations.
        emoteSuggestions (bool):
            Skype for Web (Emoticon suggestions): show popup lists of emoticons matching keywords.
        showEmotes(bool):
            Skype for Web (Show emoticons): replace text shortcuts (``:)``) with actual emoticons in conversations.
        animateEmotes (bool):
            Skype for Web (Show animated emoticons): use animated version of emoticons.
        largeEmotes (bool):
            Skype for Web (Show large emoticons): if only an emoticon in a message, display it larger.
        pinFavourites (bool):
            Skype for Web (Pin recent favorites): show favourite and recent contacts at the top of the contact list.
        darkTheme (bool):
            Skype for Web (Dark theme): use white text on a dark background.
        autoAddFriends (bool):
            Make address book contacts with Skype accounts appear in the contact list.
        callPrivacy (:class:`Privacy`):
            Who to accept incoming audio calls from.
        videoPrivacy (:class:`Privacy`):
            Who to accept incoming video and screen-share requests from.
    """

    attrs = ("notificationPopups", "notificationSounds", "callPopups", "callSounds", "webLinkPreviews",
             "youtubePlayer", "mentionNotifs", "imagePaste", "shareTyping", "emoteSuggestions", "showEmotes",
             "animateEmotes", "largeEmotes", "pinFavourites", "darkTheme", "callPrivacy", "videoPrivacy")

    Privacy = SkypeEnum("SkypeSettings.Privacy", ("Anyone", "Contacts", "Nobody"))
    """
    :class:`.SkypeEnum`: Privacy option values for incoming audio and video calls.

    Attributes:
        Privacy.Anyone
            Allow from all Skype users.
        Privacy.Contacts
            Only allow from Skype users on the connected account's contact list.
        Privacy.Nobody
            Deny from all Skype users.
    """

    def __init__(self, skype=None, raw=None):
        super(SkypeSettings, self).__init__(skype, raw)
        self.flags = set()

    def syncFlags(self):
        """
        Update the cached list of all enabled flags, and store it in the :attr:`flags` attribute.
        """
        self.flags = set(self.skype.conn("GET", SkypeConnection.API_FLAGS,
                                         auth=SkypeConnection.Auth.SkypeToken).json())

    def flagProp(id, invert=False):
        @property
        def prop(self):
            return (id in self.flags) ^ invert

        @prop.setter
        def prop(self, val):
            val = bool(val) ^ invert
            self.syncFlags()
            if not val == (id in self.flags):
                self.skype.conn("PUT" if val else "DELETE", "{0}/{1}".format(SkypeConnection.API_FLAGS, id),
                                auth=SkypeConnection.Auth.SkypeToken)
                self.flags.add(id) if val else self.flags.remove(id)
        return prop

    def apiProp(id):
        @property
        def prop(self):
            json = self.skype.conn("GET", "{0}/users/{1}/options/{2}".format(SkypeConnection.API_USER,
                                                                             self.skype.userId, id),
                                   auth=SkypeConnection.Auth.SkypeToken).json()
            return json.get("optionInt", json.get("optionStr", json.get("optionBin")))

        @prop.setter
        def prop(self, val):
            self.skype.conn("POST", "{0}/users/{1}/options/{2}".format(SkypeConnection.API_USER,
                                                                       self.skype.userId, id),
                            auth=SkypeConnection.Auth.SkypeToken, data={"integerValue": val})
        return prop

    def optProp(id):
        def idHeaders():
            return {"X-Microsoft-Skype-Message-ID": str(uuid4()),
                    "X-Microsoft-Skype-Chain-ID": str(uuid4())}

        @property
        def prop(self):
            return self.skype.conn("GET", "{0}/{1}".format(SkypeConnection.API_OPTIONS, id),
                                   auth=SkypeConnection.Auth.SkypeToken,
                                   headers=idHeaders()).json().get("value")

        @prop.setter
        def prop(self, val):
            self.skype.conn("PUT", "{0}/{1}".format(SkypeConnection.API_OPTIONS, id),
                            auth=SkypeConnection.Auth.SkypeToken,
                            headers=idHeaders(), json={"value": val})
        return prop

    notificationPopups = flagProp(21, True)
    notificationSounds = flagProp(31, True)
    callPopups = flagProp(32, True)
    callSounds = flagProp(33, True)
    webLinkPreviews = flagProp(11, True)
    youtubePlayer = flagProp(12)
    mentionNotifs = flagProp(13, True)
    imagePaste = flagProp(14)
    shareTyping = flagProp(20, True)
    emoteSuggestions = flagProp(23)
    showEmotes = flagProp(24, True)
    animateEmotes = flagProp(25, True)
    largeEmotes = flagProp(26, True)
    pinFavourites = flagProp(27, True)
    darkTheme = flagProp(28)

    # Hidden options, which are abstracted below to avoid the flag nonsense.
    callPrivacyOpt = optProp("calling.skype-call-policy")
    videoPrivacyContacts = flagProp(15)
    videoPrivacyNobody = flagProp(16)

    @property
    def callPrivacy(self):
        return self.Privacy.Anyone if self.callPrivacyOpt == "EVERYONE_CAN_CALL" else self.Privacy.Contacts

    @callPrivacy.setter
    def callPrivacy(self, val):
        self.callPrivacyOpt = "EVERYONE_CAN_CALL" if val == self.Privacy.Anyone else "AUTHORIZED_CAN_CALL"

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
