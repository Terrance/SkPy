from datetime import datetime

from .conn import SkypeConnection
from .util import SkypeObj, SkypeObjs, SkypeApiException, initAttrs, convertIds, cacheResult


@initAttrs
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
        avatar (str):
            URL to retrieve the user's profile picture.
        mood (:class:`Mood`):
            Mood message set by the user.
        chat (:class:`.SkypeSingleChat`):
            One-to-one conversation with this user.
    """

    @initAttrs
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

    @initAttrs
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

    @initAttrs
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
        location = SkypeUser.Location(city=locationParts.get("city"), region=locationParts.get("region"),
                                      country=((locationParts.get("country") or "").upper() or None))
        avatar = raw.get("avatar_url", raw.get("avatarUrl"))
        mood = None
        if raw.get("mood", raw.get("richMood")):
            mood = SkypeUser.Mood(plain=raw.get("mood"), rich=raw.get("richMood"))
        return {
            "id": raw.get("id", raw.get("username")),
            "name": name,
            "location": location,
            "avatar": avatar,
            "mood": mood
        }

    @property
    @cacheResult
    def chat(self):
        return self.skype.chats["8:" + self.id]

    def invite(self, greeting=None):
        """
        Send the user a contact request.

        Args:
            greeting (str): custom message to include with the request
        """
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}".format(SkypeConnection.API_USER, self.id),
                        json={"greeting": greeting})


@initAttrs
class SkypeContact(SkypeUser):
    """
    A user on Skype that the logged-in account is a contact of.  Allows access to contacts-only properties.

    Attributes:
        language (str):
            Two-letter language code as specified by the user.
        phones (:class:`Phone` list):
            Any phone numbers defined for the user.
        birthday (datetime.datetime):
            Date of birth of the user.
        authorised (bool):
            Whether the user has accepted an invite to become a contact.
        blocked (bool):
            Whether the logged-in account has blocked this user.
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
            Home = 0
            """
            A home phone number.
            """
            Work = 1
            """
            An office or work phone number.
            """
            Mobile = 2
            """
            A mobile phone number.
            """

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
            "language": (raw.get("language") or "").upper() or None,
            "phones": phones,
            "birthday": birthday,
            "authorised": raw.get("authorized"),
            "blocked": raw.get("blocked")
        })
        return fields

    def delete(self):
        """
        Remove the user from your contacts.
        """
        self.skype.conn("DELETE", "{0}/users/self/contacts/{1}".format(SkypeConnection.API_USER, self.id))


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
    """

    def __init__(self, skype=None):
        super(SkypeContacts, self).__init__(skype)
        self.contactIds = []

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

    def sync(self):
        for json in self.skype.conn("GET", "{0}/users/{1}/contacts"
                                           .format(SkypeConnection.API_CONTACTS, self.skype.userId),
                                    auth=SkypeConnection.Auth.SkypeToken).json().get("contacts", []):
            self.merge(SkypeContact.fromRaw(self.skype, json))
            if not json.get("suggested"):
                self.contactIds.append(json.get("id"))
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
            json = self.skype.conn("GET", "{0}/users/{1}/profile".format(SkypeConnection.API_USER, id),
                                   auth=SkypeConnection.Auth.SkypeToken).json()
            if json.get("id") not in self.contactIds:
                self.contactIds.append(json.get("id"))
            return self.merge(SkypeContact.fromRaw(self.skype, json))
        except SkypeApiException as e:
            if len(e.args) >= 2 and getattr(e.args[1], "status_code", None) == 403:
                # Not a contact, so no permission to retrieve information.
                return None
            raise

    def user(self, id):
        """
        Retrieve public information about a user.

        Note that it is not possible to distinguish if a contacts exists or not.

        An unregistered identifier produces a profile with only the identifier populated.

        Args:
            id (str): user identifier to lookup

        Returns:
            SkypeUser: resulting user object
        """
        json = self.skype.conn("POST", "{0}/users/self/contacts/profiles".format(SkypeConnection.API_USER),
                               auth=SkypeConnection.Auth.SkypeToken, data={"contacts[]": id}).json()
        return self.merge(SkypeUser.fromRaw(self.skype, json[0]))

    @cacheResult
    def search(self, query):
        """
        Search the Skype Directory for a user.

        Args:
            query (str): name to search for

        Returns:
            list: collection of possible results
        """
        search = {
            "keyWord": query,
            "contactTypes[]": "skype"
        }
        json = self.skype.conn("GET", "{0}/search/users/any".format(SkypeConnection.API_USER),
                               auth=SkypeConnection.Auth.SkypeToken, params=search).json()
        results = []
        for obj in json:
            res = obj.get("ContactCards", {}).get("Skype")
            # Make result data nesting a bit cleaner.
            res["Location"] = obj.get("ContactCards", {}).get("CurrentLocation")
            results.append(res)
        return results

    def requests(self):
        """
        Retrieve any pending contact requests.

        Returns:
            :class:`SkypeRequest` list: collection of requests
        """
        json = self.skype.conn("GET", "{0}/users/self/contacts/auth-request".format(SkypeConnection.API_USER),
                               auth=SkypeConnection.Auth.SkypeToken).json()
        requests = []
        for obj in json:
            requests.append(SkypeRequest.fromRaw(self.skype, obj))
        return requests


@initAttrs
@convertIds("user")
class SkypeRequest(SkypeObj):
    """
    A contact request.  Use :meth:`accept` or :meth:`reject` to act on it.

    Attributes:
        user (:class:`SkypeUser`):
            User that initiated the request.
        greeting (str):
            Custom message included with the request.
    """

    attrs = ("userId", "greeting")

    @classmethod
    def rawToFields(cls, raw={}):
        return {
            "userId": raw.get("sender"),
            "greeting": raw.get("greeting")
        }

    def accept(self):
        """
        Accept the contact request, and add the user to the contact list.
        """
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/accept"
                               .format(SkypeConnection.API_USER, self.userId), auth=SkypeConnection.Auth.SkypeToken)
        self.skype.conn("PUT", "{0}/users/ME/contacts/8:{1}".format(self.skype.conn.msgsHost, self.userId),
                        auth=SkypeConnection.Auth.RegToken)

    def reject(self):
        """
        Decline the contact request.
        """
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/decline"
                               .format(SkypeConnection.API_USER, self.userId), auth=SkypeConnection.Auth.SkypeToken)
