from datetime import datetime

from .conn import SkypeConnection
from .util import SkypeObj, SkypeApiException, upper, initAttrs, convertIds, cacheResult

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
        location = SkypeUser.Location(city=locationParts.get("city"), region=locationParts.get("region"),
                                      country=upper(locationParts.get("country")))
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
        """
        Return the conversation object for this user.
        """
        return self.skype.getChat("8:" + self.id)
    def invite(self, greeting=None):
        """
        Send the user a contact request.
        """
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}".format(SkypeConnection.API_USER, self.id),
                        json={"greeting": greeting})

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
    def delete(self):
        """
        Remove the user from your contacts.
        """
        self.skype.conn("DELETE", "{0}/users/self/contacts/{1}".format(SkypeConnection.API_USER, self.id))

class SkypeContacts(SkypeObj):
    """
    A container of contacts, providing caching of user info to reduce API requests.

    There are multiple ways to look up users in Skype:
    a) Requesting the whole contact list [self.sync()] -- includes most fields, as well as authorisation status.
    b) Requesting a single contact [self.contact()] -- returns all public and contact-private info.
    c) Requesting a single user [self.user()] -- only provides public information, but works with any user.
    d) Searching the Skype directory [self.search()] -- returns a collection of search results.

    When using key lookups, the individual methods are abstracted -- it uses a), with a fallback of c) for non-contacts.
    """
    def __init__(self, skype):
        super(SkypeContacts, self).__init__()
        self.skype = skype
        self.synced = False
        self.cache = {}
        self.contactIds = []
    def __getitem__(self, key):
        """
        Provide key lookups for Skype usernames.

        If the user is a contact, return their cached contact object.

        If not, retrieve their user object, cache it and return it.
        """
        if not self.synced:
            self.sync()
        if key == self.skype.userId:
            return self.skype.user
        return self.cache.get(key) or self.user(key)
    def __iter__(self):
        """
        Create an iterator for all contacts (that is, users in the contact list that are not suggestions).
        """
        if not self.synced:
            self.sync()
        for id in sorted(self.contactIds):
            yield self.cache[id]
    def merge(self, obj):
        """
        Add a given contact or user to the cache, or update an existing entry to include more fields.
        """
        if obj.id in self.cache:
            self.cache[obj.id].merge(obj)
        else:
            self.cache[obj.id] = obj
        return self.cache[obj.id]
    def sync(self):
        """
        Retrieve all contacts and store them in the cache.
        """
        for json in self.skype.conn("GET", "{0}/users/{1}/contacts".format(SkypeConnection.API_CONTACTS, self.skype.userId),
                                    auth=SkypeConnection.Auth.Skype).json().get("contacts", []):
            self.merge(SkypeContact.fromRaw(self.skype, json))
            if not json.get("suggested"):
                self.contactIds.append(json.get("id"))
        self.synced = True
    def contact(self, id):
        """
        Retrieve all details for a specific contact, including fields such as birthday and mood.
        """
        try:
            json = self.skype.conn("GET", "{0}/users/{1}/profile".format(SkypeConnection.API_USER, id),
                                   auth=SkypeConnection.Auth.Skype).json()
            if json.get("id") not in self.contactIds:
                self.contactIds.append(json.get("id"))
            return self.merge(SkypeContact.fromRaw(self.skype, json))
        except SkypeApiException as e:
            if len(e.args) >= 2 and isinstance(e.args[1], requests.Response) and e.args[1].status_code == 403:
                # Not a contact, so no permission to retrieve information.
                return None
            raise
    def user(self, id):
        """
        Retrieve public information about a user.

        Note that it is not possible to distinguish if a contacts exists or not.

        An unregistered identifier produces a profile with only the identifier populated.
        """
        json = self.skype.conn("POST", "{0}/users/self/contacts/profiles".format(SkypeConnection.API_USER),
                               auth=SkypeConnection.Auth.Skype, data={"contacts[]": id}).json()
        return self.merge(SkypeUser.fromRaw(self.skype, json[0]))
    @cacheResult
    def search(self, query):
        """
        Search the Skype Directory for a user.
        """
        search = {
            "keyWord": query,
            "contactTypes[]": "skype"
        }
        json = self.skype.conn("GET", "{0}/search/users/any".format(SkypeConnection.API_USER),
                               auth=SkypeConnection.Auth.Skype, params=search).json()
        results = []
        for obj in json:
            res = obj.get("ContactCards", {}).get("Skype")
            # Make result data nesting a bit cleaner.
            res["Location"] = obj.get("ContactCards", {}).get("CurrentLocation")
            results.append(res)
        return results

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
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/accept".format(SkypeConnection.API_USER, self.userId),
                        auth=SkypeConnection.Auth.Skype)
        self.skype.conn("PUT", "{0}/users/ME/contacts/8:{1}".format(self.skype.conn.msgsHost, self.userId),
                        auth=SkypeConnection.Auth.Reg)
    def reject(self):
        self.skype.conn("PUT", "{0}/users/self/contacts/auth-request/{1}/decline".format(SkypeConnection.API_USER, self.userId),
                        auth=SkypeConnection.Auth.Skype)
