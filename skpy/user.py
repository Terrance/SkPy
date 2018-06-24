from datetime import datetime

from .core import SkypeObj, SkypeObjs, SkypeEnum, SkypeApiException
from .util import SkypeUtils
from .conn import SkypeConnection
from .chat import SkypeSingleChat


@SkypeUtils.initAttrs
class SkypeUser(SkypeObj):
    """
    A user on Skype -- the current one, a contact, or someone else.

    Properties differ slightly between the current user and others.  Only public properties are available here.

    Searches different possible attributes for each property.  Also deconstructs a merged first name field.

    Attributes:
        id (str):
            Username of the user.
        name (:class:`Name`):
            Representation of the user's name.
        location (:class:`Location`):
            Geographical information provided by the user.
        language (str):
            Two-letter language code as specified by the user.
        avatar (str):
            URL to retrieve the user's profile picture.
        mood (:class:`Mood`):
            Mood message set by the user.
        chat (:class:`.SkypeSingleChat`):
            One-to-one conversation with this user.
    """

    @SkypeUtils.initAttrs
    @SkypeUtils.truthyAttrs
    class Name(SkypeObj):
        """
        The name of a user or contact.

        Attributes:
            first (str):
                First and middle names of the user.
            last (str):
                Surname of the user.
        """

        attrs = ("first", "last")

        def __str__(self):
            return " ".join(filter(None, (self.first, self.last)))

    @SkypeUtils.initAttrs
    @SkypeUtils.truthyAttrs
    class Location(SkypeObj):
        """
        The location of a user or contact.

        Any number of fields may be filled in, so stringifying will combine them into a comma-separated list.

        Attributes:
            city (str):
                Town or city where the user is located.
            region (str):
                State or region where they are located.
            country (str):
                Two-letter country code for their location.
        """

        attrs = ("city", "region", "country")

        def __str__(self):
            return ", ".join(filter(None, (self.city, self.region, self.country)))

    @SkypeUtils.initAttrs
    class Mood(SkypeObj):
        """
        The mood message set by a user or contact.

        Attributes:
            plain (str):
                Plain text representation of a user's mood.
            rich (str):
                Mood message with original formatting.
        """

        attrs = ("plain", "rich")

        def __str__(self):
            return self.plain or self.rich or ""

    attrs = ("id", "name", "location", "language", "avatar", "mood")
    defaults = dict(name=Name(), location=Location())

    @classmethod
    def rawToFields(cls, raw={}):
        id = SkypeUtils.noPrefix(raw.get("id", raw.get("mri", raw.get("skypeId", raw.get("username")))))
        name = raw.get("name")
        if isinstance(name, str):
            # Unified name provided by directory.
            firstName = name
            lastName = None
        elif isinstance(name, dict):
            # Name object from contact APIs.
            firstName = name.get("first")
            lastName = name.get("last", name.get("surname"))
        else:
            # Individual first/last name keys.
            firstName = raw.get("firstname")
            lastName = raw.get("lastname")
        # Some clients stores the whole name in the user's first name field.
        if not lastName and firstName and " " in firstName:
            firstName, lastName = firstName.rsplit(" ", 1)
        name = SkypeUser.Name(first=firstName, last=lastName)
        if "locations" in raw:
            locParts = raw.get("locations")[0]
        else:
            locParts = {"city": raw.get("city"),
                        "region": raw.get("province", raw.get("state")),
                        "country": raw.get("countryCode", raw.get("country"))}
        location = SkypeUser.Location(city=locParts.get("city"), region=locParts.get("region"),
                                      country=((locParts.get("country") or "").upper() or None))
        language = (raw.get("language") or "").upper() or None
        avatar = raw.get("avatar_url", raw.get("avatarUrl"))
        mood = None
        if raw.get("mood", raw.get("richMood")):
            mood = SkypeUser.Mood(plain=raw.get("mood"), rich=raw.get("richMood"))
        return {"id": id,
                "name": name,
                "location": location,
                "language": language,
                "avatar": avatar,
                "mood": mood}

    @property
    @SkypeUtils.cacheResult
    def chat(self):
        prefix = "28" if isinstance(self, SkypeBotUser) else "8"
        try:
            return self.skype.chats["{0}:{1}".format(prefix, self.id)]
        except SkypeApiException:
            # Maybe a conversation doesn't exist yet, return a disconnected one instead.
            return SkypeSingleChat(self.skype, id="{}:{}".format(prefix, self.id), alerts=True, userId=self.id)

    def invite(self, greeting=None):
        """
        Send the user a contact request.

        Args:
            greeting (str): custom message to include with the request
        """
        if not greeting:
            greeting = "Hi, {0}, I'd like to add you as a contact.".format(self.name)
        prefix = "28" if isinstance(self, SkypeBotUser) else "8"
        self.skype.conn("POST", "{0}/users/{1}/contacts".format(SkypeConnection.API_CONTACTS, self.skype.userId),
                        auth=SkypeConnection.Auth.SkypeToken, json={"mri": "{0}:{1}".format(prefix, self.id),
                                                                    "greeting": greeting})

    def block(self, report=False):
        """
        Block the user from all communication.

        Args:
            report (bool): whether to report this user to Skype
        """
        prefix = "28" if isinstance(self, SkypeBotUser) else "8"
        self.skype.conn("PUT", "{0}/users/{1}/contacts/blocklist/{2}:{3}"
                               .format(SkypeConnection.API_CONTACTS, self.skype.userId, prefix, self.id),
                        auth=SkypeConnection.Auth.SkypeToken, json={"report_abuse": report, "ui_version": "skype.com"})
        self.blocked = True

    def unblock(self):
        """
        Unblock a previously blocked user.
        """
        prefix = "28" if isinstance(self, SkypeBotUser) else "8"
        self.skype.conn("DELETE", "{0}/users/{1}/contacts/blocklist/{2}:{3}"
                                  .format(SkypeConnection.API_CONTACTS, self.skype.userId, prefix, self.id),
                        auth=SkypeConnection.Auth.SkypeToken)
        self.blocked = False


@SkypeUtils.initAttrs
class SkypeContact(SkypeUser):
    """
    A user on Skype that the logged-in account is a contact of.  Allows access to contacts-only properties.

    Attributes:
        phones (:class:`Phone` list):
            Any phone numbers defined for the user.
        birthday (datetime.datetime):
            Date of birth of the user.
        authorised (bool):
            Whether the user has accepted an invite to become a contact.
        blocked (bool):
            Whether the logged-in account has blocked this user.
        favourite (bool):
            Whether the contact is marked as a favourite by the logged-in user.
    """

    @SkypeUtils.initAttrs
    class Phone(SkypeObj):
        """
        The phone number of a contact.
        """

        Type = SkypeEnum("SkypeContact.Phone.Type", ("Home", "Work", "Mobile"))
        """
        :class:`.SkypeEnum`: Types of phone number.

        Attributes:
            Type.Home:
                A home phone number.
            Type.Work:
                An office or work phone number.
            Type.Mobile:
                A mobile phone number.
        """

        attrs = ("type", "number")

        def __str__(self):
            return self.number or ""

    attrs = SkypeUser.attrs + ("phones", "birthday", "authorised", "blocked", "favourite")
    defaults = dict(SkypeUser.defaults, phones=[])

    @classmethod
    def rawToFields(cls, raw={}):
        fields = super(SkypeContact, cls).rawToFields(raw)
        phonesMap = {"Home": SkypeContact.Phone.Type.Home,
                     "Office": SkypeContact.Phone.Type.Work,
                     "Mobile": SkypeContact.Phone.Type.Mobile}
        phonesParts = raw.get("phones", [])
        for k in phonesMap:
            if raw.get("phone" + k):
                phonesParts.append({"type": phonesMap[k], "number": raw.get("phone" + k)})
        phones = [SkypeContact.Phone(type=p["type"], number=p["number"]) for p in phonesParts]
        try:
            birthday = datetime.strptime(raw.get("birthday") or "", "%Y-%m-%d").date()
        except ValueError:
            birthday = None
        fields.update({"phones": phones,
                       "birthday": birthday,
                       "authorised": raw.get("authorized"),
                       "blocked": raw.get("blocked"),
                       "favourite": raw.get("favorite")})
        return fields

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        usrCls = SkypeBotUser if raw.get("type") == "agent" else cls
        return usrCls(skype, raw, **usrCls.rawToFields(raw))

    def delete(self):
        """
        Remove the user from your contacts.
        """
        self.skype.conn("DELETE", "{0}/users/{1}/contacts/8:{2}"
                                  .format(SkypeConnection.API_CONTACTS, self.skype.userId, self.id),
                        auth=SkypeConnection.Auth.SkypeToken)
        self.skype.conn("DELETE", "{0}/users/ME/contacts/8:{1}".format(self.skype.conn.msgsHost, self.id),
                        auth=SkypeConnection.Auth.RegToken)


@SkypeUtils.initAttrs
class SkypeBotUser(SkypeUser):
    """
    A server-side bot account.  In most cases, they act like a normal user -- they can be added as contacts, interacted
    with in one-to-one conversations, or invited to groups if the bot supports it.

    Attributes:
        name (str):
            Display name of the bot.
        developer (str):
            Display name of the bot's developer.
        trusted (bool):
            Whether the bot is official and provided by Skype or Microsoft.
        locales (str list):
            Country-language codes supported by the bot.
        rating (float):
            User-provided rating of the bot.
        description (str):
            Information about what the bot does.
        extra (str):
            Footer info, such as hyperlinks to privacy and terms.
        siteUrl (str):
            URL for the bot's website.
        termsUrl (str):
            URL for the bot's terms of service.
        privacyUrl (str):
            URL for the bot's privacy policy.
    """

    attrs = SkypeUser.attrs + ("developer", "trusted", "locales", "rating", "description", "extra",
                               "siteUrl", "termsUrl", "privacyUrl")
    defaults = {"name": None, "location": None}

    @classmethod
    def rawToFields(cls, raw={}):
        # Bot users don't really share any common fields with normal users, but we still want a subclass.
        return {"id": raw.get("agentId", raw.get("id")),
                "name": raw.get("displayName", raw.get("display_name", raw.get("name", {}).get("first"))),
                "location": None,
                "avatar": raw.get("userTileStaticUrl", raw.get("userTileExtraLargeUrl", raw.get("avatar_url"))),
                "mood": None,
                "developer": raw.get("developer", raw.get("name", {}).get("company")),
                "trusted": raw.get("isTrusted"),
                "locales": raw.get("supportedLocales"),
                "rating": raw.get("starRating"),
                "description": raw.get("description"),
                "extra": raw.get("extra"),
                "siteUrl": raw.get("webpage"),
                "termsUrl": raw.get("tos"),
                "privacyUrl": raw.get("privacyStatement")}

    @property
    @SkypeUtils.cacheResult
    def chat(self):
        return self.skype.chats["28:" + self.id]


class SkypeContacts(SkypeObjs):
    """
    A container of contacts, providing caching of user info to reduce API requests.

    There are multiple ways to look up users in Skype:

    - Requesting the whole contact list -- includes most fields, as well as authorisation status.
    - Requesting a single contact (:meth:`contact`) -- returns all public and contact-private info.
    - Requesting a single user (:meth:`user`) -- only provides public information, but works with any user.
    - Searching the Skype directory (:meth:`search`) -- returns a collection of search results.

    When using key lookups, it checks the contact list first, with a user fallback for non-contacts.

    Contacts can also be iterated over, where only authorised users are returned in the collection.

    Attributes:
        groups (dict):
            Set of :class:`SkypeContactGroup` instances, keyed by group name.
        blocked (SkypeContactGroup):
            Group of users blocked from all communication.
    """

    def __init__(self, skype=None):
        super(SkypeContacts, self).__init__(skype)
        self.contactIds = []
        self.groups = {}

    def __getitem__(self, key):
        # Try to retrieve from the cache, otherwise return a user object instead.
        try:
            return super(SkypeContacts, self).__getitem__(key)
        except KeyError:
            return self.skype.user if key == self.skype.userId else self.user(key)

    def __iter__(self):
        if not self.synced:
            self.sync()
        # Only iterate over actual contacts, not all cached users.
        for id in sorted(self.contactIds):
            yield self.cache[id]

    def __len__(self):
        if not self.synced:
            self.sync()
        return len(self.contactIds)

    def sync(self):
        resp = self.skype.conn("GET", "{0}/users/{1}".format(SkypeConnection.API_CONTACTS, self.skype.userId),
                               params={"delta": "", "reason": "default"},
                               auth=SkypeConnection.Auth.SkypeToken).json()
        for json in resp.get("contacts", []):
            # Merge nested profile key into self.
            json.update(json.get("profile", {}))
            # Favourite property only exists if true, else default it to false (doesn't appear in other API requests).
            json["favorite"] = json.get("favorite", False)
            contact = SkypeContact.fromRaw(self.skype, json)
            self.merge(contact)
            if not json.get("suggested"):
                self.contactIds.append(contact.id)
        for json in resp.get("groups", []):
            self.groups[json.get("name", json.get("id"))] = SkypeContactGroup.fromRaw(self.skype, json)
        blocked = resp.get("blocklist", [])
        self.blocked = SkypeContactGroup(self.skype, blocked, userIds=[block.get("mri") for block in blocked])
        super(SkypeContacts, self).sync()

    def contact(self, id):
        """
        Retrieve all details for a specific contact, including fields such as birthday and mood.

        Args:
            id (str): user identifier to lookup

        Returns:
            SkypeContact: resulting contact object
        """
        try:
            json = self.skype.conn("POST", "{0}/users/batch/profiles".format(SkypeConnection.API_USER),
                                   json={"usernames": [id]}, auth=SkypeConnection.Auth.SkypeToken).json()
            contact = SkypeContact.fromRaw(self.skype, json[0])
            if contact.id not in self.contactIds:
                self.contactIds.append(contact.id)
            return self.merge(contact)
        except SkypeApiException as e:
            if len(e.args) >= 2 and getattr(e.args[1], "status_code", None) == 403:
                # Not a contact, so no permission to retrieve information.
                return None
            raise

    def user(self, id):
        """
        Retrieve public information about a user.

        Args:
            id (str): user identifier to lookup

        Returns:
            SkypeUser: resulting user object
        """
        json = self.skype.conn("POST", "{0}/batch/profiles".format(SkypeConnection.API_PROFILE),
                               auth=SkypeConnection.Auth.SkypeToken, json={"usernames": [id]}).json()
        if json and "status" not in json[0]:
            return self.merge(SkypeUser.fromRaw(self.skype, json[0]))
        else:
            return None

    @SkypeUtils.cacheResult
    def bots(self):
        """
        Retrieve a list of all known bots.

        Returns:
            SkypeBotUser list: resulting bot user objects
        """
        json = self.skype.conn("GET", "{0}/agents".format(SkypeConnection.API_BOT),
                               auth=SkypeConnection.Auth.SkypeToken).json().get("agentDescriptions", [])
        return [self.merge(SkypeBotUser.fromRaw(self.skype, raw)) for raw in json]

    def bot(self, id):
        """
        Retrieve a single bot.

        Args:
            id (str): UUID or username of the bot

        Returns:
            SkypeBotUser: resulting bot user object
        """
        json = self.skype.conn("GET", "{0}/agents".format(SkypeConnection.API_BOT), params={"agentId": id},
                               auth=SkypeConnection.Auth.SkypeToken).json().get("agentDescriptions", [])
        return self.merge(SkypeBotUser.fromRaw(self.skype, json[0])) if json else None

    @SkypeUtils.cacheResult
    def search(self, query):
        """
        Search the Skype Directory for a user.

        Args:
            query (str): name to search for

        Returns:
            SkypeUser list: collection of possible results
        """
        results = self.skype.conn("GET", SkypeConnection.API_DIRECTORY,
                                  auth=SkypeConnection.Auth.SkypeToken,
                                  params={"searchstring": query, "requestId": "0"}).json().get("results", [])
        return [SkypeUser.fromRaw(self.skype, json.get("nodeProfileData", {})) for json in results]

    def requests(self):
        """
        Retrieve any pending contact requests.

        Returns:
            :class:`SkypeRequest` list: collection of requests
        """
        requests = []
        for json in self.skype.conn("GET", "{0}/users/{1}/invites"
                                           .format(SkypeConnection.API_CONTACTS, self.skype.userId),
                                    auth=SkypeConnection.Auth.SkypeToken).json().get("invite_list", []):
            for invite in json.get("invites", []):
                # Copy user identifier to each invite message.
                invite["userId"] = SkypeUtils.noPrefix(json.get("mri"))
                requests.append(SkypeRequest.fromRaw(self.skype, invite))
        return requests


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("users")
class SkypeContactGroup(SkypeObj):
    """
    A user-defined collection of contacts.  Currently read-only in the API.

    Attributes:
        id (str):
            Unique identifier for this group.
        name (str):
            Display name as set by the user.
        contacts (:class:`SkypeContact` list):
            Contacts added to this group.
    """

    attrs = ("id", "name", "userIds")

    @classmethod
    def rawToFields(cls, raw={}):
        return {"id": raw.get("id"),
                "name": raw.get("name"),
                "userIds": [SkypeUtils.noPrefix(id) for id in raw.get("contacts", [])]}


@SkypeUtils.initAttrs
@SkypeUtils.convertIds("user")
class SkypeRequest(SkypeObj):
    """
    A contact request.  Use :meth:`accept` or :meth:`reject` to act on it.

    Attributes:
        user (:class:`SkypeUser`):
            User that initiated the request.
        greeting (str):
            Custom message included with the request.
        time (datetime.datetime):
            Time and date when the invite was sent.
    """

    attrs = ("userId", "greeting", "time")

    @classmethod
    def rawToFields(cls, raw={}):
        return {"userId": raw.get("userId"),
                "greeting": raw.get("message"),
                "time": datetime.strptime(raw.get("time", ""), "%Y-%m-%dT%H:%M:%SZ")}

    def accept(self):
        """
        Accept the contact request, and add the user to the contact list.
        """
        self.skype.conn("PUT", "{0}/users/{1}/invites/8:{2}/accept"
                               .format(SkypeConnection.API_CONTACTS, self.skype.userId, self.userId),
                        auth=SkypeConnection.Auth.SkypeToken)
        self.skype.conn("PUT", "{0}/users/ME/contacts/8:{1}".format(self.skype.conn.msgsHost, self.userId),
                        auth=SkypeConnection.Auth.RegToken)

    def reject(self):
        """
        Decline the contact request.
        """
        self.skype.conn("PUT", "{0}/users/{1}/invites/8:{2}/decline"
                               .format(SkypeConnection.API_CONTACTS, self.skype.userId, self.userId),
                        auth=SkypeConnection.Auth.SkypeToken)
