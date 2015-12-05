from __future__ import unicode_literals

import re
from collections import Hashable
from functools import partial, wraps

def upper(s):
    """
    Shorthand to uppercase a string, and leave None as None.
    """
    return s if s == None else s.upper()

def noPrefix(s):
    """
    Remove the type prefix from a chat identifier.
    """
    return s if s == None else s.split(":", 1)[1]

def userToId(url):
    """
    Extract the username from a contact URL.
    """
    match = re.search(r"/v1/users/ME/contacts/[0-9]+:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None

def chatToId(url):
    """
    Extract the conversation ID from a conversation URL.
    """
    match = re.search(r"/v1/users/ME/conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None

def initAttrs(cls):
    """
    Class decorator: automatically generate an __init__ method that expects args from cls.attrs and stores them.

    Drops any unrecognised properties from kwargs.
    """
    def __init__(self, skype=None, raw=None, *args, **kwargs):
        super(cls, self).__init__(skype, raw)
        # Merge args into kwargs based on cls.attrs.
        for i in range(len(args)):
            kwargs[cls.attrs[i]] = args[i]
        # Set each attribute from kwargs, or use the default if not specified.
        for k in cls.attrs:
            setattr(self, k, kwargs.get(k, cls.defaults.get(k)))
    # Add the init method to the class.
    setattr(cls, "__init__", __init__)
    return cls

def convertIds(*types, user=(), users=(), chat=()):
    """
    Class decorator: add helper methods to convert identifier properties into SkypeObjs.
    """
    def userObj(self, field):
        """
        Retrieve the user referred to in the object.
        """
        userId = getattr(self, field)
        return self.skype.getContact(userId) or self.skype.getUser(userId)
    def userObjs(self, field):
        """
        Retrieve all users referred to in the object.
        """
        userIds = getattr(self, field)
        return ((self.skype.getContact(id) or self.skype.getUser(id)) for id in userIds)
    def chatObj(self, field):
        """
        Retrieve the user referred to in the object.
        """
        return self.skype.getChat(getattr(self, field))
    def attach(cls, method, field, idField):
        """
        Generate the property object and attach it to the class.
        """
        setattr(cls, field, property(partial(method, field=idField)))
    def wrapper(cls):
        # Shorthand identifiers, e.g. @convertIds("user", "chat").
        for type in types:
            if type == "user":
                attach(cls, userObj, "user", "userId")
            elif type == "users":
                attach(cls, userObjs, "users", "userIds")
            elif type == "chat":
                attach(cls, chatObj, "chat", "chatId")
        # Custom field names, e.g. @convertIds(user=["creator"]).
        for field in user:
            attach(cls, userObj, field, "{0}Id".format(field))
        for field in users:
            attach(cls, userObjs, "{0}s.".format(field), "{0}Ids".format(field))
        for field in chat:
            attach(cls, chatObj, field, "{0}Id".format(field))
        return cls
    return wrapper

def cacheResult(fn):
    """
    Decorator: calculate the value on first access, produce the cached value thereafter.

    If the function takes an argument, the cache is a dictionary using the first argument as a key.
    """
    cache = {}
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = args + (str(kwargs),)
        if not all(isinstance(x, Hashable) for x in key):
            # Can't cache with non-hashable args (e.g. a list).
            return fn(*args, **kwargs)
        if key not in cache:
            cache[key] = fn(*args, **kwargs)
        return cache[key]
    # Make cache accessible externally.
    wrapper.cache = cache
    return wrapper

def syncState(fn):
    """
    Decorator: follow state-sync links when provided by an API.

    The function being wrapped must return: url, params, fetch(url, params), process(resp)
    """
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        # The wrapped function should be defined to return these.
        url, params, fetch, process = fn(self, *args, **kwargs)
        if wrapper.state:
            # We have a state link, use that instead of the default URL.
            url = wrapper.state[-1]
            params = {}
        # Store the new state link.
        resp, state = fetch(url, params)
        wrapper.state.append(state)
        return process(resp)
    # Make state links accessible externally.
    wrapper.state = []
    return wrapper

def exhaust(fn, init, *args, **kwargs):
    """
    Repeatedly call a function, starting with init, until false-y, then combine all sets.

    Use with state-synced functions to retrieve all results.
    """
    while True:
        iterRes = fn(*args, **kwargs)
        if iterRes:
            if isinstance(init, dict):
                init.update(iterRes)
            else:
                init += iterRes
        else:
            break
    return init

class SkypeException(Exception):
    """
    A generic Skype-related exception.
    """
    pass

class SkypeApiException(SkypeException):
    """
    An exception thrown for errors specific to external API calls.

    Args will usually be of the form (message, response).
    """
    pass

class SkypeObj(object):
    """
    A basic Skype-related object.  Holds references to the parent Skype instance, and the raw dict from the API.

    The attrs property should be set to the named attributes for that class, with defaults to override None for certain attributes.
    """
    attrs = ()
    defaults = {}
    def __init__(self, skype=None, raw=None):
        """
        Store a reference to the Skype object for later API calls.

        Most implementers don't need to override this method directly, use @initAttrs instead.
        """
        self.skype = skype
        self.raw = raw
    @classmethod
    def rawToFields(cls, raw={}):
        """
        Convert the raw properties of an API response into class fields.  Override to process additional values.
        """
        return {}
    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        """
        Create a new instance based on the raw properties of an API response.
        """
        return cls(skype, raw, **cls.rawToFields(raw))
    def __str__(self):
        """
        Pretty print the object, based on the class' attrs parameter.  Produces output something like:

        [<class name>]
        <attribute>: <value>

        Nested objects are indented as needed.
        """
        out = "[{0}]".format(self.__class__.__name__)
        for attr in self.attrs:
            value = getattr(self, attr)
            valStr = ("\n".join(str(i) for i in value) if isinstance(value, list) else str(value))
            out += "\n{0}{1}: {2}".format(attr[0].upper(), attr[1:], valStr.replace("\n", "\n  " + (" " * len(attr))))
        return out
    def __repr__(self):
        """
        Dump properties of the object into a Python-like statement, based on the class' attrs parameter.

        The resulting string is an expression that should evaluate to a similar object, minus Skype connection.
        """
        return "{0}({1})".format(self.__class__.__name__, ", ".join("{0}={1}".format(k, repr(getattr(self, k))) for k in self.attrs))
