import re

def objToStr(obj, *attrs):
    out = "[{0}]".format(obj.__class__.__name__)
    for attr in attrs:
        out += "\n{0}: {1}".format(attr.capitalize(), str(getattr(obj, attr)).replace("\n", "\n  " + (" " * len(attr))))
    return out

def userToId(url):
    match = re.search(r"/v1/users/ME/contacts/8:([A-Za-z0-9\.,_-]+)", url)
    return match.group(1) if match else None

def chatToId(url):
    match = re.search(r"/v1/users/ME/conversations/([0-9]+:[A-Za-z0-9\.,_-]+(@thread\.skype)?)", url)
    return match.group(1) if match else None

class SkypeObj(object):
    def __init__(self, conn, raw):
        self.conn = conn
        self.raw = raw
    def __repr__(self):
        return "<{0}: {1}>".format(self.__class__.__name__, self.id)
