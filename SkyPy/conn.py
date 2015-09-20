import os
import datetime
import time
import hashlib

import bs4
import requests

class SkypeConnection(object):
    class Auth:
        Skype, Reg = range(2)
    API_LOGIN = "https://login.skype.com/login?client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com"
    API_MSGSHOST = "https://client-s.gateway.messenger.live.com/v1/users/ME"
    def __init__(self, user=None, pwd=None, tokenFile=None):
        self.tokens = {}
        self.tokenExpiry = {}
        if tokenFile and os.path.isfile(tokenFile):
            with open(tokenFile, "r") as f:
                skypeToken, skypeExpiry, regToken, msgsHost = f.read().splitlines()
                skypeExpiry = datetime.datetime.fromtimestamp(int(skypeExpiry))
                if datetime.datetime.now() < skypeExpiry:
                    self.tokens["skype"] = skypeToken
                    self.tokenExpiry["skype"] = skypeExpiry
                    self.tokens["reg"] = regToken
                    self.msgsHost = msgsHost
        if not self.tokens:
            self.login(user, pwd)
            self.msgsHost = self.API_MSGSHOST
            self.getRegToken()
            if tokenFile:
                with open(tokenFile, "w") as f:
                    f.write(self.tokens["skype"] + "\n")
                    f.write(str(int(time.mktime(self.tokenExpiry["skype"].timetuple()))) + "\n")
                    f.write(self.tokens["reg"] + "\n")
                    f.write(self.msgsHost + "\n")
        self.subscribe()
    def __call__(self, method, url, codes=[200, 201], auth=None, headers={}, data=None, json=None):
        if auth == self.Auth.Skype:
            headers["X-SkypeToken"] = self.tokens["skype"]
        elif auth == self.Auth.Reg:
            headers["RegistrationToken"] = self.tokens["reg"]
        resp = requests.request(method, url, headers=headers, data=data, json=json)
        if resp.status_code not in codes:
            raise SkypeApiException("{0} response from {1} {2}".format(resp.status_code, method, url), resp)
        return resp
    def login(self, user, pwd):
        loginPage = bs4.BeautifulSoup(self("GET", self.API_LOGIN).text, "html.parser")
        if loginPage.find(id="recaptcha_response_field"):
            raise SkypeApiException("Captcha required")
        pie = loginPage.find(id="pie").get("value")
        etm = loginPage.find(id="etm").get("value")
        secs = int(time.time())
        loginResp = self("POST", self.API_LOGIN, data={
            "username": user,
            "password": pwd,
            "pie": pie,
            "etm": etm,
            "timezone_field": "+00|00", # TODO: use the correct value
            "js_time": secs
        })
        loginRespPage = bs4.BeautifulSoup(loginResp.text, "html.parser")
        try:
            self.tokens["skype"] = loginRespPage.find("input", {"name": "skypetoken"}).get("value")
            self.tokenExpiry["skype"] = datetime.datetime.fromtimestamp(secs + int(loginRespPage.find("input", {"name": "expires_in"}).get("value")))
        except AttributeError as e:
            raise SkypeApiException("Couldn't retrieve Skype token from login response", loginResp)
    def getRegToken(self):
        secs = int(time.time())
        endpointResp = self("POST", self.msgsHost + "/endpoints", codes=[201, 301], headers={
            "LockAndKey": "appId=msmsgs@msnmsgr.com; time=" + str(secs) + "; lockAndKeyResponse=" + getMac256Hash(str(secs), "msmsgs@msnmsgr.com", "Q1P7W2E4J9R8U3S5"),
            "ClientInfo": "os=Windows; osVer=10; proc=Win64; lcid=en-us; deviceType=1; country=n/a; clientName=swx-skype.com; clientVer=908/1.7.251",
            "Authentication": "skypetoken=" + self.tokens["skype"]
        }, json={})
        location = endpointResp.headers["Location"].rsplit("/", 2)[0]
        regTokenHead = endpointResp.headers["Set-RegistrationToken"]
        if not location == self.msgsHost:
            self.msgsHost = location
            return self.getRegToken()
        self.tokens["reg"] = regTokenHead
    def subscribe(self):
        self("POST", self.msgsHost + "/endpoints/SELF/subscriptions", auth=self.Auth.Reg, json={
            "interestedResources": [
                "/v1/threads/ALL",
                "/v1/users/ME/contacts/ALL",
                "/v1/users/ME/conversations/ALL/messages",
                "/v1/users/ME/conversations/ALL/properties"
            ],
            "template": "raw",
            "channelType": "httpLongPoll"
        })

class SkypeApiException(Exception):
    pass

def getMac256Hash(challenge, appId, key):
    def padRight(original, totalWidth, ch):
        def stringFromChar(ch, count):
            s = ch
            for i in range(1, count):
                s += ch
            return s
        if len(original) < totalWidth:
            ch = ch or " "
            return original + stringFromChar(ch, totalWidth - len(original))
        else:
            return original.valueOf()
    def int32ToHexString(n):
        hexChars = "0123456789abcdef"
        hexString = ""
        for i in range(4):
            hexString += hexChars[(n >> (i * 8 + 4)) & 15]
            hexString += hexChars[(n >> (i * 8)) & 15]
        return hexString
    def int64Xor(a, b):
        sA = "{0:b}".format(a)
        sB = "{0:b}".format(b)
        sC = ""
        sD = ""
        diff = abs(len(sA) - len(sB))
        for i in range(diff):
            sD += "0"
        if len(sA) < len(sB):
            sD += sA
            sA = sD
        elif len(sB) < len(sA):
            sD += sB
            sB = sD
        for i in range(len(sA)):
            sC += "0" if sA[i] == sB[i] else "1"
        return int(sC, 2)
    def cS64_C(pdwData, pInHash):
        if len(pdwData) < 2 or len(pdwData) & 1 == 1:
            return None
        MODULUS = 2147483647
        CS64_a = pInHash[0] & MODULUS
        CS64_b = pInHash[1] & MODULUS
        CS64_c = pInHash[2] & MODULUS
        CS64_d = pInHash[3] & MODULUS
        CS64_e = 242854337
        pos = 0
        qwDatum = 0
        qwMAC = 0
        qwSum = 0
        for i in range(len(pdwData) / 2):
            qwDatum = int(pdwData[pos])
            pos += 1
            qwDatum *= CS64_e
            qwDatum = qwDatum % MODULUS
            qwMAC += qwDatum
            qwMAC *= CS64_a
            qwMAC += CS64_b
            qwMAC = qwMAC % MODULUS
            qwSum += qwMAC
            qwMAC += int(pdwData[pos])
            pos += 1
            qwMAC *= CS64_c
            qwMAC += CS64_d
            qwMAC = qwMAC % MODULUS
            qwSum += qwMAC
        qwMAC += CS64_b
        qwMAC = qwMAC % MODULUS
        qwSum += CS64_d
        qwSum = qwSum % MODULUS
        return [qwMAC, qwSum]
    clearText = challenge + appId
    remaining = 8 - len(clearText) % 8
    if remaining != 8:
        clearText = padRight(clearText, len(clearText) + remaining, "0")
    cchClearText = len(clearText) / 4
    pClearText = []
    pos = 0
    for i in range(cchClearText):
        pClearText = pClearText[:i] + [0] + pClearText[i:]
        pClearText[i] += ord(clearText[pos]) * 1
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 256
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 65536
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 16777216
        pos += 1
    sha256Hash = [0, 0, 0, 0]
    hash = hashlib.sha256(challenge + key).hexdigest().upper()
    pos = 0
    for i in range(len(sha256Hash)):
        sha256Hash[i] = 0
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 1
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 256
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 65536
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 16777216
        pos += 2
    macHash = cS64_C(pClearText, sha256Hash)
    a = int64Xor(sha256Hash[0], macHash[0])
    b = int64Xor(sha256Hash[1], macHash[1])
    c = int64Xor(sha256Hash[2], macHash[0])
    d = int64Xor(sha256Hash[3], macHash[1])
    return int32ToHexString(a) + int32ToHexString(b) + int32ToHexString(c) + int32ToHexString(d)