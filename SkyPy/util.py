import re

def userToId(url):
    match = re.search(r"/v1/users/ME/contacts/8:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None

def chatToId(url):
    match = re.search(r"/v1/users/ME/conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None

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
