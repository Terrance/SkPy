from __future__ import unicode_literals

import re
import functools

from .core import SkypeEnum
from .conn import SkypeConnection


class SkypeUtils:
    """
    A collection of miscellaneous static methods used throughout the library.

    Attributes:
        config (dict):
            Raw object containing miscellaneous server-side flags and configuration.
        static (dict):
            Raw object containing emoticons and packs.
    """

    Status = SkypeEnum("SkypeUtils.Status", ("Offline", "Hidden", "Busy", "Away", "Idle", "Online"))
    """
    :class:`.SkypeEnum`: Types of user availability.

    Attributes:
        Status.Offline:
            User is not connected.
        Status.Hidden:
            User is pretending to be offline.  Shows as hidden to the current user, offline to anyone else.
        Status.Busy:
            User wishes not to be disturbed.  Disables notifications on some clients (e.g. on the desktop).
        Status.Away:
            User has explicitly marked themselves as away.  Alternatively, this may just be an alias for idle.
        Status.Idle:
            User is online but not active.  Messages will likely be delivered as normal, though may not be read.
        Status.Online:
            User is available to talk.
    """

    @staticmethod
    def noPrefix(s):
        """
        Remove the type prefix from a chat identifier (e.g. ``8:`` for a one-to-one, ``19:`` for a group).

        Args:
            s (str): string to transform

        Returns:
            str: unprefixed string
        """
        return None if s is None else re.sub("^[0-9]+:", "", s)

    @staticmethod
    def userToId(url):
        """
        Extract the username from a contact URL.

        Matches addresses containing ``users/<user>`` or ``users/ME/contacts/<user>``.

        Args:
            url (str): Skype API URL

        Returns:
            str: extracted identifier
        """
        match = re.search(r"users(/ME/contacts)?/[0-9]+:([^/]+)", url)
        return match.group(2) if match else None

    @staticmethod
    def chatToId(url):
        """
        Extract the conversation ID from a conversation URL.

        Matches addresses containing ``conversations/<chat>``.

        Args:
            url (str): Skype API URL

        Returns:
            str: extracted identifier
        """
        match = re.search(r"conversations/([0-9]+:[^/]+)", url)
        return match.group(1) if match else None

    class classprop(property):
        """
        Method decorator: allows designating class methods as properties.
        """

        def __get__(self, cls, owner):
            return self.fget.__get__(None, owner)()

    @staticmethod
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
                raise TypeError("__init__() got {0} {1}".format(unknownDesc, unknownList))
            # Set each attribute from kwargs, or use the default if not specified.
            for k in cls.attrs:
                setattr(self, k, kwargs.get(k, cls.defaults.get(k)))

        # Add the init method to the class.
        setattr(cls, "__init__", __init__)
        return cls

    @staticmethod
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
            setattr(cls, field, property(functools.wraps(fn)(functools.partial(fn, field=idField))))

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

    @staticmethod
    def truthyAttrs(cls):
        """
        Class decorator: override __bool__ to set truthiness based on any attr being present.

        Args:
            cls (class): class to decorate

        Returns:
            class: same, but modified, class
        """
        def __bool__(self):
            return bool(any(getattr(self, attr) for attr in self.attrs))

        cls.__bool__ = cls.__nonzero__ = __bool__
        return cls

    # This is used below, so don't make it static yet.
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

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Imperfect key generation (args may be passed as kwargs, so multiple ways to represent one key).
            key = args + tuple(kwargs.items())
            # Order of operations here tries to minimise use of exceptions.
            try:
                # Don't call the function here, as it may throw a TypeError itself (or from incorrect arguments).
                if key in cache:
                    return cache[key]
            except TypeError:
                # Key is not hashable, so we can't cache with these args -- just return the result.
                return fn(*args, **kwargs)
            # Not yet cached, so generate the result and store it.
            cache[key] = fn(*args, **kwargs)
            return cache[key]

        # Make cache accessible externally.
        wrapper.cache = cache
        return wrapper

    @staticmethod
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

    @classprop
    @classmethod
    @cacheResult
    def config(cls):
        # Fetch the current assets URL, and follow that to retrieve the static content.
        return SkypeConnection.externalCall("GET", "{0}/SkypeLyncWebExperience/0_0.0.0.0"
                                                   .format(SkypeConnection.API_CONFIG),
                                            params={"apikey": "skype.com"}).json()

    @classprop
    @classmethod
    @cacheResult
    def static(cls):
        # Fetch the current assets URL, and follow that to retrieve the static content.
        json = SkypeConnection.externalCall("GET", "{0}/Skype/0_0.0.0.0/SkypePersonalization"
                                                   .format(SkypeConnection.API_CONFIG)).json()
        return SkypeConnection.externalCall("GET", json.get("pes_config")).json()

    # Now wrap this decorator as a static method.
    cacheResult = staticmethod(cacheResult)
