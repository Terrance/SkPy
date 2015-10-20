import re
import functools
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

def userToId(url):
    match = re.search(r"/v1/users/ME/contacts/8:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None

def chatToId(url):
    match = re.search(r"/v1/users/ME/conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None

def lazyLoad(fn):
    cachedAttr = "{0}Cached".format(fn.__name__)
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, cachedAttr):
            setattr(self, cachedAttr, fn(self, *args, **kwargs))
        return getattr(self, cachedAttr)
    return wrapper

def stateLoad(fn):
    cachedAttr = "{0}Cached".format(fn.__name__)
    stateAttr = "{0}State".format(fn.__name__)
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        url, params, fetch, process = fn(self, *args, **kwargs)
        if hasattr(self, stateAttr):
            queryUrl = getattr(self, stateAttr)
            query = urlparse.parse_qsl(queryUrl.split("?", 1)[1], keep_blank_values=True)#
            url = queryUrl.split("?")[0]
            params = {}
            for k, v in query:
                if k not in params:
                    params[k] = v
        resp, state = fetch(url, params)
        setattr(self, stateAttr, state)
        setattr(self, cachedAttr, process(resp))
        return getattr(self, cachedAttr)
    return wrapper

class SkypeObj(object):
    attrs = []
    def __init__(self, skype, raw):
        self.skype = skype
        self.raw = raw
    def __str__(self):
        out = "[{0}]".format(self.__class__.__name__)
        for attr in self.attrs:
            out += "\n{0}: {1}".format(attr[0].upper() + attr[1:], str(getattr(self, attr)).replace("\n", "\n  " + (" " * len(attr))))
        return out
    def __repr__(self):
        return "{0}({1})".format(self.__class__.__name__, ", ".join("{0}={1}".format(k, repr(getattr(self, k))) for k in self.attrs))
