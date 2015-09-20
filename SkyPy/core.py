import time

from conn import SkypeConnection

class Skype(object):
    def __init__(self, user, pwd):
        self.conn = SkypeConnection(user, pwd)
        self.getUser()
        self.getContacts()
    def getUser(self):
        self.user = self.conn("GET", "https://api.skype.com/users/self/displayname", auth=SkypeConnection.Auth.Skype).json()
    def getContacts(self):
        self.contacts = self.conn("GET", "https://contacts.skype.com/contacts/v1/users/" + self.user["username"] + "/contacts", auth=SkypeConnection.Auth.Skype).json()["contacts"]
    def getEvents(self):
        return self.conn("POST", self.conn.msgsHost + "/endpoints/SELF/subscriptions/0/poll", auth=SkypeConnection.Auth.Reg).json()["eventMessages"]
    def sendMsg(self, conv, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = self.req("POST", self.conn.msgsHost + "/conversations/" + conv + "/messages", auth=SkypeConnection.Auth.Reg, json={
            "clientmessageid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        return msgId
    def __repr__(self):
        return "<Skype: " + self.user["username"] + ">"
