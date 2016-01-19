import os
import re
from functools import partial, wraps
from datetime import datetime
import time
import math
import hashlib

from bs4 import BeautifulSoup
import requests

from .util import SkypeObj, SkypeException, SkypeApiException

class SkypeConnection(SkypeObj):
    """
    The main connection class -- handles all requests to API resources.

    An instance of this class is callable, and performs an API request.

    Arguments are similar to the underlying requests library.
    """
    class Auth:
        """
        Enum: authentication types.  Skype uses X-SkypeToken, whereas Reg includes RegistrationToken.
        """
        SkypeToken, Authorize, RegToken = range(3)
    attrs = ("user", "tokenFile")
    @staticmethod
    def handle(*codes, **kwargs):
        """
        Decorator: if a given status code is received, reauthenticate and try again.
        """
        regToken = kwargs.get("regToken", False)
        def decorator(fn):
            @wraps(fn)
            def wrapper(self, *args, **kwargs):
                try:
                    return fn(self, *args, **kwargs)
                except SkypeApiException as e:
                    if isinstance(e.args[1], requests.Response) and e.args[1].status_code in codes:
                        conn = self if isinstance(self, SkypeConnection) else self.conn
                        if regToken:
                            conn.getRegToken()
                        return fn(self, *args, **kwargs)
                    raise
            return wrapper
        return decorator
    API_LOGIN = "https://login.skype.com/login?client_id=578134&redirect_uri=https%3A%2F%2Fweb.skype.com"
    API_USER = "https://api.skype.com"
    API_SCHEDULE = "https://api.scheduler.skype.com"
    API_CONTACTS = "https://contacts.skype.com/contacts/v1"
    API_MSGSHOST = "https://client-s.gateway.messenger.live.com/v1"
    def __init__(self, user=None, pwd=None, tokenFile=None):
        """
        Initialise a new Skype connection.

        If tokenFile is specified, it is searched for valid tokens.  If all is well, no further handshake is required.

        Otherwise, if user and pwd are set, try to interact with login.skype.com and fetch tokens.
        """
        self.tokens = {}
        self.tokenExpiry = {}
        self.tokenFile = tokenFile
        self.msgsHost = self.API_MSGSHOST
        self.endpoints = {"self": SkypeEndpoint(self, "SELF")}
        if user and pwd:
            # Create a method to reauthenticate with login.skype.com (avoids storing the password in an accessible way).
            self.getSkypeToken = partial(self.login, user, pwd)
        if tokenFile and os.path.isfile(tokenFile):
            try:
                with open(tokenFile, "r") as f:
                    self.user, skypeToken, skypeExpiry, regToken, regExpiry, msgsHost = f.read().splitlines()
                skypeExpiry = datetime.fromtimestamp(int(skypeExpiry))
                regExpiry = datetime.fromtimestamp(int(regExpiry))
                if datetime.now() >= skypeExpiry:
                    # We want to ignore this (see except block).
                    raise SkypeException("Token file has expired")
            except:
                # Expired or otherwise can't read the file, skip to user/pwd authentication.
                pass
            else:
                self.tokens["skype"] = skypeToken
                self.tokenExpiry["skype"] = skypeExpiry
                if datetime.now() < regExpiry:
                    self.tokens["reg"] = regToken
                    self.tokenExpiry["reg"] = regExpiry
                    self.msgsHost = msgsHost
                    # No need to write the token file.
                    return
                else:
                    self.getRegToken()
        if not self.tokens:
            if not hasattr(self, "getSkypeToken"):
                raise SkypeException("No username or password provided, and no valid token file")
            self.getSkypeToken()
            self.getRegToken()
    def __call__(self, method, url, codes=(200, 201, 207), auth=None, headers=None, **kwargs):
        """
        Make an API call.  Most parameters are passed directly to requests.

        Set codes to a list of valid HTTP response codes -- an exception is raised if the response does not match.

        If authentication is required, set auth to one of the SkypeConnection.Auth constants.
        """
        self.verifyToken(auth)
        if not headers:
            headers = {}
        if auth == self.Auth.SkypeToken:
            headers["X-SkypeToken"] = self.tokens["skype"]
        elif auth == self.Auth.Authorize:
            headers["Authorization"] = "skype_token {0}".format(self.tokens["skype"])
        elif auth == self.Auth.RegToken:
            headers["RegistrationToken"] = self.tokens["reg"]
        resp = requests.request(method, url, headers=headers, **kwargs)
        if resp.status_code not in codes:
            if resp.status_code == 429:
                raise SkypeAuthException("Auth rate limit exceeded", resp)
            raise SkypeApiException("{0} response from {1} {2}".format(resp.status_code, method, url), resp)
        return resp
    def login(self, user, pwd):
        """
        Scrape the Skype Web login page, and perform a login with the given username and password.
        """
        loginResp = self("GET", self.API_LOGIN)
        loginPage = BeautifulSoup(loginResp.text, "html.parser")
        if loginPage.find(id="captcha"):
            raise SkypeAuthException("Captcha required", loginResp)
        pie = loginPage.find(id="pie").get("value")
        etm = loginPage.find(id="etm").get("value")
        secs = int(time.time())
        frac, hour = math.modf(time.timezone)
        timezone = "{0:+03d}|{1}".format(int(hour), int(frac * 60))
        loginResp = self("POST", self.API_LOGIN, data={
            "username": user,
            "password": pwd,
            "pie": pie,
            "etm": etm,
            "timezone_field": timezone,
            "js_time": secs
        })
        loginRespPage = BeautifulSoup(loginResp.text, "html.parser")
        errors = loginRespPage.select("div.messageBox.message_error span")
        if errors:
            raise SkypeAuthException(errors[0].text, loginResp)
        try:
            self.tokens["skype"] = loginRespPage.find("input", {"name": "skypetoken"}).get("value")
            length = int(loginRespPage.find("input", {"name": "expires_in"}).get("value"))
            self.tokenExpiry["skype"] = datetime.fromtimestamp(secs + length)
            self.user = user
        except AttributeError as e:
            raise SkypeApiException("Couldn't retrieve Skype token from login response", loginResp)
    def getRegToken(self):
        """
        Acquire a registration token.  See getMac256Hash(...) for the hash generation.
        """
        self.verifyToken(self.Auth.SkypeToken)
        secs = int(time.time())
        hash = getMac256Hash(str(secs), "msmsgs@msnmsgr.com", "Q1P7W2E4J9R8U3S5")
        endpointResp = self("POST", "{0}/users/ME/endpoints".format(self.msgsHost), codes=[201, 301], headers={
            "LockAndKey": "appId=msmsgs@msnmsgr.com; time={0}; lockAndKeyResponse={1}".format(secs, hash),
            "Authentication": "skypetoken=" + self.tokens["skype"]
        }, json={})
        locParts = endpointResp.headers["Location"].rsplit("/", 4)
        msgsHost = locParts[0]
        endId = locParts[4]
        regTokenHead = endpointResp.headers["Set-RegistrationToken"]
        if not msgsHost == self.msgsHost:
            self.msgsHost = msgsHost
            return self.getRegToken()
        self.endpoints["main"] = SkypeEndpoint(self, endId)
        self.tokens["reg"] = re.search(r"(registrationToken=[a-z0-9\+/=]+)", regTokenHead, re.I).group(1)
        self.tokenExpiry["reg"] = datetime.fromtimestamp(int(re.search(r"expires=(\d+)", regTokenHead).group(1)))
        if self.tokenFile:
            with open(self.tokenFile, "w") as f:
                f.write(self.user + "\n")
                f.write(self.tokens["skype"] + "\n")
                f.write(str(int(time.mktime(self.tokenExpiry["skype"].timetuple()))) + "\n")
                f.write(self.tokens["reg"] + "\n")
                f.write(str(int(time.mktime(self.tokenExpiry["reg"].timetuple()))) + "\n")
                f.write(self.msgsHost + "\n")
    def verifyToken(self, auth):
        """
        Ensure the authentication token for the given auth method is still valid.
        """
        if auth in (self.Auth.SkypeToken, self.Auth.Authorize):
            if "skype" in self.tokenExpiry and datetime.now() >= self.tokenExpiry["skype"]:
                if not hasattr(self, "getSkypeToken"):
                    raise SkypeException("Skype token expired, and no password specified")
                self.getSkypeToken()
        elif auth == self.Auth.RegToken:
            if "reg" in self.tokenExpiry and datetime.now() >= self.tokenExpiry["reg"]:
                self.getRegToken()

class SkypeEndpoint(object):
    """
    An endpoint represents a single point of presence within Skype.

    Typically, a user with multiple devices would have one endpoint per device (desktop, laptop, mobile and so on).

    Endpoints are time-sensitive -- they lapse after a very short time unless kept alive (with ping() or other methods).
    """
    def __init__(self, conn, id):
        """
        Create a new instance based on a newly-created endpoint identifier.
        """
        self.conn = conn
        self.id = id
        self.subscribed = False
    def ping(self, timeout=12):
        """
        Send a keep-alive request for the endpoint.

        The timeout specifies the maximum amount of time for the endpoint to stay active unless pinged again.
        """
        self.conn("POST", "{0}/users/ME/endpoints/{1}/active".format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken, json={"timeout": timeout})
    def subscribe(self):
        """
        Subscribe to contact and conversation events.  These are accessible through Skype.getEvents().
        """
        meta = {
            "interestedResources": [
                "/v1/threads/ALL",
                "/v1/users/ME/contacts/ALL",
                "/v1/users/ME/conversations/ALL/messages",
                "/v1/users/ME/conversations/ALL/properties"
            ],
            "template": "raw",
            "channelType": "httpLongPoll"
        }
        self.conn("POST", "{0}/users/ME/endpoints/{1}/subscriptions".format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken, json=meta)
        self.subscribed = True
    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events occur, the API will block for up to 30 seconds, after which an empty list is returned.

        If any event occurs whilst blocked, it is returned immediately.
        """
        if not self.subscribed:
            self.subscribe()
        events = []
        return self.conn("POST", "{0}/users/ME/endpoints/{1}/subscriptions/0/poll".format(self.conn.msgsHost, self.id),
                         auth=SkypeConnection.Auth.RegToken).json().get("eventMessages", [])
    def __str__(self):
        return "[{0}]\nId: {1}".format(self.__class__.__name__, self.id)
    def __repr__(self):
        return "{0}(id={1})".format(self.__class__.__name__, repr(self.id))

class SkypeAuthException(SkypeException):
    """
    An exception thrown when authentication cannot be completed.

    Generally this means the request should not be retried (e.g. incorrect password), or a cooldown is needed (rate limits).
    """
    pass

def getMac256Hash(challenge, appId, key):
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
    def cS64(pdwData, pInHash):
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
        for i in range(len(pdwData) // 2):
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
    clearText += "0" * (8 - len(clearText) % 8)
    cchClearText = len(clearText) // 4
    pClearText = []
    for i in range(cchClearText):
        pClearText = pClearText[:i] + [0] + pClearText[i:]
        for pos in range(4):
            pClearText[i] += ord(clearText[pos]) * (256 ** pos)
    sha256Hash = [0, 0, 0, 0]
    hash = hashlib.sha256((challenge + key).encode("utf-8")).hexdigest().upper()
    for i in range(len(sha256Hash)):
        sha256Hash[i] = 0
        for pos in range(4):
            dpos = pos * 2
            sha256Hash[i] += int(hash[dpos:dpos + 2], 16) * (256 ** pos)
    macHash = cS64(pClearText, sha256Hash)
    macParts = [macHash[0], macHash[1], macHash[0], macHash[1]]
    return "".join(map(int32ToHexString, map(int64Xor, sha256Hash, macParts)))
