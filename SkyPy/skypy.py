import re
import time
import urlparse
import requests
import bs4

import util

class Skype:
    def __init__(self, user, pwd):
        self.login(user, pwd)
        self.msgsHost = "client-s.gateway.messenger.live.com"
        self.getRegToken()
        self.subscribe()
        self.getUser()
        self.getContacts()
    def login(self, user, pwd):
        loginURL = "https://login.skype.com/login?client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com"
        loginPage = bs4.BeautifulSoup(requests.get(loginURL).text, "html.parser")
        pie = loginPage.find(id="pie").get("value")
        etm = loginPage.find(id="etm").get("value")
        secs = int(time.time())
        respPage = bs4.BeautifulSoup(requests.post(loginURL, data={
            "username": user,
            "password": pwd,
            "pie": pie,
            "etm": etm,
            "timezone_field": "+00|00", # TODO: use the correct value
            "js_time": secs
        }).text, "html.parser")
        self.token = respPage.find("input", {"name": "skypetoken"}).get("value")
        self.expires = respPage.find("input", {"name": "expires_in"}).get("value")
    def getRegToken(self):
        secs = int(time.time())
        endpointResp = requests.post("https://" + self.msgsHost + "/v1/users/ME/endpoints", headers={
            "LockAndKey": "appId=msmsgs@msnmsgr.com; time=" + str(secs) + "; lockAndKeyResponse=" + util.getMac256Hash(str(secs), "msmsgs@msnmsgr.com", "Q1P7W2E4J9R8U3S5"),
            "ClientInfo": "os=Windows; osVer=10; proc=Win64; lcid=en-us; deviceType=1; country=n/a; clientName=swx-skype.com; clientVer=908/1.7.251",
            "Authentication": "skypetoken=" + self.token
        }, json={})
        assert endpointResp.status_code in [201, 301]
        location = endpointResp.headers["Location"]
        regTokenHead = endpointResp.headers["Set-RegistrationToken"]
        host = urlparse.urlparse(location).hostname
        if not host == self.msgsHost:
            self.msgsHost = host
            return self.getRegToken()
        self.regToken = {
            "raw": regTokenHead
        }
        for part in re.split("\s*;\s*", regTokenHead):
            if part.index("=") >= 0:
                k, v = part.split("=")
                self.regToken[k] = v
        assert "registrationToken" in self.regToken
        assert "endpointId" in self.regToken
        assert "expires" in self.regToken
    def subscribe(self):
        subResp = requests.post("https://" + self.msgsHost + "/v1/users/ME/endpoints/SELF/subscriptions", headers={
            "RegistrationToken": self.regToken["raw"]
        }, json={
            "interestedResources": [
                "/v1/threads/ALL",
                "/v1/users/ME/contacts/ALL",
                "/v1/users/ME/conversations/ALL/messages",
                "/v1/users/ME/conversations/ALL/properties"
            ],
            "template": "raw",
            "channelType": "httpLongPoll"
        })
        assert subResp.status_code == 201
    def getUser(self):
        userResp = requests.get("https://api.skype.com/users/self/displayname", headers={
            "X-SkypeToken": self.token
        })
        assert userResp.status_code == 200
        self.user = userResp.json()
    def getContacts(self):
        contResp = requests.get("https://contacts.skype.com/contacts/v1/users/" + self.user["username"] + "/contacts", headers={
            "X-SkypeToken": self.token
        })
        assert contResp.status_code == 200
        self.contacts = contResp.json()["contacts"]
    def getEvents(self):
        eventsResp = requests.post("https://" + self.msgsHost + "/v1/users/ME/endpoints/SELF/subscriptions/0/poll", headers={
            "RegistrationToken": self.regToken["raw"]
        })
        assert eventsResp.status_code == 200
        return eventsResp.json()["eventMessages"]
    def sendMsg(self, conv, msg, edit=None):
        msgId = edit or int(time.time())
        msgResp = requests.post("https://" + self.msgsHost + "/v1/users/ME/conversations/" + conv + "/messages", headers={
            "RegistrationToken": self.regToken["raw"]
        }, json={
            "clientmessageid": msgId,
            "messagetype": "RichText",
            "contenttype": "text",
            "content": msg
        })
        assert msgResp.status_code == 201
        return msgId
    def __repr__(self):
        return "<Skype: " + self.user["username"] + ">"