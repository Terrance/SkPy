from datetime import datetime

from .conn import SkypeConnection
from .util import SkypeObj, upper, initAttrs, convertIds, cacheResult

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
