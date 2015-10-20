import re
import functools
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

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

def lazyLoad(fn):
    """
    Decorator: calculate the value on first access, produce the cached value thereafter.
    """
    cachedAttr = "{0}Cached".format(fn.__name__)
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, cachedAttr):
            setattr(self, cachedAttr, fn(self, *args, **kwargs))
        return getattr(self, cachedAttr)
    return wrapper

def stateLoad(fn):
    """
    Decorator: follow state-sync links when provided by an API.

    The function being wrapped must return: url, params, fetch(url, params), process(resp)
    """
    stateAttr = "{0}State".format(fn.__name__)
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        url, params, fetch, process = fn(self, *args, **kwargs)
        if hasattr(self, stateAttr):
            url = getattr(self, stateAttr)
            params = {}
        resp, state = fetch(url, params)
        setattr(self, stateAttr, state)
        return process(resp)
    return wrapper

class SkypeObj(object):
    """
    A basic Skype-related object.  Holds references to the parent Skype instance, and the raw dict from the API.
    """
    attrs = []
    def __init__(self, skype, raw):
        self.skype = skype
        self.raw = raw
    def __str__(self):
        """
        Pretty print the object, based on the class' attrs parameter.  Produces output something like:

        [<class name>]
        <attribute>: <value>

        Nested objects are indented as needed.
        """
        out = "[{0}]".format(self.__class__.__name__)
        for attr in self.attrs:
            out += "\n{0}: {1}".format(attr[0].upper() + attr[1:], str(getattr(self, attr)).replace("\n", "\n  " + (" " * len(attr))))
        return out
    def __repr__(self):
        """
        Dump properties of the object into a Python-like statement, based on the class' attrs parameter.

        The resulting string is not executable (such objects don't take individual parameters).
        """
        return "{0}({1})".format(self.__class__.__name__, ", ".join("{0}={1}".format(k, repr(getattr(self, k))) for k in self.attrs))
