from __future__ import unicode_literals

import re
from collections import Hashable
from functools import partial, wraps


def noPrefix(s):
    """
    Remove the type prefix from a chat identifier (e.g. ``8:`` for a one-to-one, ``19:`` for a group).

    Args:
        s (str): string to transform

    Returns:
        str: unprefixed string
    """
    return s if s is None else s.split(":", 1)[1]


def userToId(url):
    """
    Extract the username from a contact URL.

    Matches addresses containing ``users/<user>`` or ``users/ME/contacts/<user>``.

    Args:
        url (str): Skype API URL

    Returns:
        str: extracted identifier
    """
    match = re.search(r"users(/ME/contacts)?/[0-9]+:([A-Za-z0-9\.,:_\-]+)", url)
    return match.group(2) if match else None


def chatToId(url):
    """
    Extract the conversation ID from a conversation URL.

    Matches addresses containing ``conversations/<chat>``.

    Args:
        url (str): Skype API URL

    Returns:
        str: extracted identifier
    """
    match = re.search(r"conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None


def initAttrs(cls):
    """
    Class decorator: automatically generate an ``__init__`` method that expects args from cls.attrs and stores them.

    Args:
        cls (class): class to decorate

    Returns:
        class: same, but modified, class
    """

    def __init__(self, skype=None, raw=None, *args, **kwargs):
        super(cls, self).__init__(skype, raw)
        # Merge args into kwargs based on cls.attrs.
        for i in range(len(args)):
            kwargs[cls.attrs[i]] = args[i]
        # Disallow any unknown kwargs.
        unknown = set(kwargs) - set(cls.attrs)
        if unknown:
            unknownDesc = "an unexpected keyword argument" if len(unknown) == 1 else "unexpected keyword arguments"
            unknownList = ", ".join("'{0}'".format(k) for k in sorted(unknown))
            raise TypeError("TypeError: __init__() got {0} {1}".format(unknownDesc, unknownList))
        # Set each attribute from kwargs, or use the default if not specified.
        for k in cls.attrs:
            setattr(self, k, kwargs.get(k, cls.defaults.get(k)))

    # Add the init method to the class.
    setattr(cls, "__init__", __init__)
    return cls


def convertIds(*types, **kwargs):
    """
    Class decorator: add helper methods to convert identifier properties into SkypeObjs.

    Args:
        types (str list): simple field types to add properties for (``user``, ``users`` or ``chat``)
        user (str list): attribute names to treat as single user identifier fields
        users (str list): attribute names to treat as user identifier lists
        chat (str list): attribute names to treat as chat identifier fields

    Returns:
        method: decorator function, ready to apply to other methods
    """

    user = kwargs.get("user", ())
    users = kwargs.get("users", ())
    chat = kwargs.get("chat", ())

    def userObj(self, field):
        return self.skype.contacts[getattr(self, field)]

    def userObjs(self, field):
        return (self.skype.contacts[id] for id in getattr(self, field))

    def chatObj(self, field):
        return self.skype.chats[getattr(self, field)]

    def attach(cls, fn, field, idField):
        """
        Generate the property object and attach it to the class.

        Args:
            cls (type): class to attach the property to
            fn (method): function to be attached
            field (str): attribute name for the new property
            idField (str): reference field to retrieve identifier from
        """
        setattr(cls, field, property(wraps(fn)(partial(fn, field=idField))))

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
            attach(cls, userObjs, "{0}s".format(field), "{0}Ids".format(field))
        for field in chat:
            attach(cls, chatObj, field, "{0}Id".format(field))
        return cls

    return wrapper


def cacheResult(fn):
    """
    Method decorator: calculate the value on first access, produce the cached value thereafter.

    If the function takes arguments, the cache is a dictionary using all arguments as the key.

    Args:
        fn (method): function to decorate

    Returns:
        method: wrapper function with caching
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
    Method decorator: follow state-sync links when provided by an API.

    Functions implementing this flow must return a tuple containing the following:

    - ``url`` (`str`): original URL to follow with no state
    - ``params`` (`dict`): keyword parameters to add to the url
    - ``fetch(url, params)`` (`method`): function to do the API request, returning the response and a new state URL
    - ``process(resp)`` (`method`): function to handle the response returned from ``fetch``

    Args:
        fn (method): function to decorate

    Returns:
        method: wrapper function with state-syncing
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


def exhaust(fn, transform=None, *args, **kwargs):
    """
    Repeatedly call a function, starting with init, until false-y, yielding each item in turn.

    The ``transform`` parameter can be used to map a collection to another format, for example iterating over a
    :class:`dict` by value rather than key.

    Use with state-synced functions to retrieve all results.

    Args:
        fn (method): function to call
        transform (method): secondary function to convert result into an iterable
        args (list): positional arguments to pass to ``fn``
        kwargs (dict): keyword arguments to pass to ``fn``

    Returns:
        generator: generator of objects produced from the method
    """
    while True:
        iterRes = fn(*args, **kwargs)
        if iterRes:
            for item in transform(iterRes) if transform else iterRes:
                yield item
        else:
            break


class SkypeObj(object):
    """
    A basic Skype object.  Holds references to the parent :class:`.Skype` instance, and a raw object from the API.

    Attributes:
        attrs (tuple):
            List of defined fields for the class.  Used by :meth:`initAttrs` to create an :meth:`__init__` method.
        defaults (dict):
            Collection of default values when any keyword arguments are omitted from the constructor.
        skype (:class:`.Skype`):
            Parent Skype instance.
        raw (dict):
            Raw object, as provided by the API.
    """

    attrs = ()
    defaults = {}

    def __init__(self, skype=None, raw=None):
        """
        Instantiate a plain instance of this class, and store a reference to the Skype object for later API calls.

        Normally this method won't be called or implemented directly.

        Implementers should make use of :meth:`fromRaw` and the :meth:`initAttrs` decorator instead.

        Args:
            skype (Skype): parent Skype instance
            raw (dict): raw object, as provided by the API
        """
        self.skype = skype
        self.raw = raw

    @classmethod
    def rawToFields(cls, raw={}):
        """
        Convert the raw properties of an API response into class fields.  Override to process additional values.

        Args:
            raw (dict): raw object, as provided by the API

        Returns:
            dict: a collection of fields, with keys matching :attr:`attrs`
        """
        return {}

    @classmethod
    def fromRaw(cls, skype=None, raw={}):
        """
        Create a new instance based on the raw properties of an API response.

        This can be overridden to automatically create subclass instances based on the raw content.

        Args:
            skype (Skype): parent Skype instance
            raw (dict): raw object, as provided by the API

        Returns:
            SkypeObj: the new class instance
        """
        return cls(skype, raw, **cls.rawToFields(raw))

    def merge(self, other):
        """
        Copy properties from other into self, skipping ``None`` values.  Also merges the raw data.

        Args:
            other (SkypeObj): second object to copy fields from
        """
        for attr in self.attrs:
            if not getattr(other, attr, None) is None:
                setattr(self, attr, getattr(other, attr))
        if other.raw:
            if not self.raw:
                self.raw = {}
            self.raw.update(other.raw)

    def __str__(self):
        """
        Pretty print the object, based on the class' attrs parameter.  Produces output something like::

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
        reprs = []
        for attr in self.attrs:
            val = getattr(self, attr)
            if not val == self.defaults.get(attr):
                reprs.append("{0}={1}".format(attr, repr(val)))
        return "{0}({1})".format(self.__class__.__name__, ", ".join(reprs))


class SkypeObjs(SkypeObj):
    """
    A basic Skype collection.  Acts as a container for objects of a given type.

    Attributes:
        synced (bool):
            Whether an initial set of objects has been cached.
        cache (dict):
            Storage of objects by identifier key.
    """

    def __init__(self, skype=None):
        """
        Create a new container object.  The :attr:`synced` state and internal :attr:`cache` are initialised here.

        Args:
            skype (Skype): parent Skype instance
        """
        super(SkypeObjs, self).__init__(skype)
        self.synced = False
        self.cache = {}

    def __getitem__(self, key):
        """
        Provide key lookups for items in the cache.  Subclasses may override this to handle not-yet-cached objects.
        """
        if not self.synced:
            self.sync()
        return self.cache[key]

    def __iter__(self):
        """
        Create an iterator for all objects (not their keys) in this collection.
        """
        if not self.synced:
            self.sync()
        for id in sorted(self.cache):
            yield self.cache[id]

    def sync(self):
        """
        Subclasses can implement this method to retrieve an initial set of objects.
        """
        self.synced = True

    def merge(self, obj):
        """
        Add a given object to the cache, or update an existing entry to include more fields.

        Args:
            obj (SkypeObj): object to add to the cache
        """
        if obj.id in self.cache:
            self.cache[obj.id].merge(obj)
        else:
            self.cache[obj.id] = obj
        return self.cache[obj.id]


class SkypeException(Exception):
    """
    A generic Skype-related exception.
    """


class SkypeApiException(SkypeException):
    """
    An exception thrown for errors specific to external API calls.

    Arguments will usually be of the form (``message``, ``response``).
    """
