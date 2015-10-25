from __future__ import unicode_literals

import re
from functools import wraps
from inspect import getargspec

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

def convertIds(*types):
    """
    Class decorator: add helper methods to convert identifier properties into SkypeObjs.
    """
    @property
    def user(self):
        """
        Retrieve the user referred to in the event.
        """
        return self.skype.getContact(self.userId)
    @property
    def chat(self):
        """
        Retrieve the conversation referred to in the event.
        """
        return self.skype.getChat(self.chatId)
    def wrapper(cls):
        if "user" in types:
            setattr(cls, "user", user)
        if "chat" in types:
            setattr(cls, "chat", chat)
        return cls
    return wrapper

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
        # We're popping from the end, so reverse the order.
        for k in cls.attrs:
            # Set each attribute from kwargs, or use the default if not specified.
            setattr(self, k, kwargs.get(k, cls.defaults.get(k)))
    # Add the init method to the class.
    setattr(cls, "__init__", __init__)
    return cls

def cacheResult(fn):
    """
    Decorator: calculate the value on first access, produce the cached value thereafter.

    If the function takes an argument, the cache is a dictionary using that argument as a key.
    """
    cacheAttr = "{0}Cache".format(fn.__name__)
    # Inspect the function for a list of argument names, skipping the self argument.
    argSpec = getargspec(fn)
    argNames = argSpec.args[1:]
    if len(argNames) > 1:
        raise RuntimeError("can't cache results if function takes multiple args")
    argName = argNames[0] if len(argNames) else None
    if argName:
        if argSpec.defaults:
            # The argument has a default value, make it optional in the wrapper.
            @wraps(fn)
            def wrapper(self, arg=argSpec.defaults[0]):
                # Use a dict to store return values based on the input.
                if not hasattr(self, cacheAttr):
                    setattr(self, cacheAttr, {})
                cache = getattr(self, cacheAttr)
                if arg not in cache:
                    # Not cached, make the function call and store the result.
                    cache[arg] = fn(self, arg)
                return cache[arg]
        else:
            # No default for the argument.
            @wraps(fn)
            def wrapper(self, arg):
                if not hasattr(self, cacheAttr):
                    setattr(self, cacheAttr, {})
                cache = getattr(self, cacheAttr)
                if arg not in cache:
                    cache[arg] = fn(self, arg)
                return cache[arg]
    else:
        # No argument, just store the single result produced by this method.
        @wraps(fn)
        def wrapper(self):
            if not hasattr(self, cacheAttr):
                setattr(self, cacheAttr, fn(self))
            return getattr(self, cacheAttr)
    return wrapper

def syncState(fn):
    """
    Decorator: follow state-sync links when provided by an API.

    The function being wrapped must return: url, params, fetch(url, params), process(resp)
    """
    stateAttr = "{0}State".format(fn.__name__)
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        # The wrapped function should be defined to return these.
        url, params, fetch, process = fn(self, *args, **kwargs)
        if hasattr(self, stateAttr):
            # We have a state link, use that instead of the default URL.
            url = getattr(self, stateAttr)
            params = {}
        resp, state = fetch(url, params)
        # Store the new state link.
        setattr(self, stateAttr, state)
        return process(resp)
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
            value = "{0}".format(getattr(self, attr)).replace("\n", "\n  " + (" " * len(attr)))
            out += "\n{0}{1}: {2}".format(attr[0].upper(), attr[1:], value)
        return out
    def __repr__(self):
        """
        Dump properties of the object into a Python-like statement, based on the class' attrs parameter.

        The resulting string is an expression that should evaluate to a similar object, minus Skype connection.
        """
        return "{0}({1})".format(self.__class__.__name__, ", ".join("{0}={1}".format(k, repr(getattr(self, k))) for k in self.attrs))
