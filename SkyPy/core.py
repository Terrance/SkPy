import time

from conn import SkypeConnection

class Skype(object):
    def __init__(self, user, pwd):
        self.conn = SkypeConnection(user, pwd)
        self.getUser()
        self.getContacts()
    def getUser(self):
        self.user = self.conn("GET", "https://api.skype.com/users/self/displayname", auth=SkypeConnection.AUTH_SKYPETOKEN).json()
    def getContacts(self):
        self.contacts = self.conn("GET", "https://contacts.skype.com/contacts/v1/users/" + self.user["username"] + "/contacts", auth=SkypeConnection.AUTH_SKYPETOKEN).json()["contacts"]
    def getEvents(self):
        return self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.AUTH_REGTOKEN).json()["eventMessages"]
    def sendMsg(self, conv, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = self.req("POST", self.conn.msgsHost + "/conversations/" + conv + "/messages", auth=SkypeConnection.AUTH_REGTOKEN, json={
            "clientmessageid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        return msgId
    def __repr__(self):
        return "<Skype: " + self.user["username"] + ">"