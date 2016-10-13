import os
import re
import functools
from datetime import datetime, timedelta
import time
from types import MethodType
import hashlib

from bs4 import BeautifulSoup
import requests

from .core import SkypeObj, SkypeEnum, SkypeException, SkypeApiException

if os.getenv("SKPY_DEBUG_HTTP"):
    from pprint import pformat


class SkypeConnection(SkypeObj):
    """
    The main connection class -- handles all requests to API resources.

    To authenticate with a username and password, use :meth:`setUserPwd` to store the credentials.  Token files can be
    specified with :meth:`setTokenFile`.

    Attributes:
        tokens (dict):
            Token strings used to connect to various Skype APIs.  Uses keys ``skype`` and ``reg``.
        tokenExpiry (dict):
            Map from token key to :class:`datetime <datetime.datetime>` of expiry.
        tokenFile (str):
            Path to file holding token data for the current session.
        msgsHost (str):
            Derived API base URL during registration token retrieval.
        sess (requests.Session):
            Shared session used for all API requests.
        endpoints (dict):
            Container of :class:`SkypeEndpoint` instances for the current session.
        connected (bool):
            Whether the connection instance is ready to make API calls.
        guest (bool):
            Whether the connected account only has guest privileges.
    """

    Auth = SkypeEnum("SkypeConnection.Auth", ("SkypeToken", "Authorize", "RegToken"))
    """
    :class:`.SkypeEnum`: Authentication types for different API calls.

    Attributes:
        Auth.SkypeToken:
            Add an ``X-SkypeToken`` header with the Skype token.
        Auth.Authorize:
            Add an ``Authorization`` header with the Skype token.
        Auth.RegToken:
            Add a ``RegistrationToken`` header with the registration token.
    """

    @staticmethod
    def handle(*codes, **kwargs):
        """
        Method decorator: if a given status code is received, re-authenticate and try again.

        Args:
            codes (int list): status codes to respond to
            regToken (bool): whether to try retrieving a new token on error

        Returns:
            method: decorator function, ready to apply to other methods
        """
        regToken = kwargs.get("regToken", False)
        subscribe = kwargs.get("subscribe")

        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(self, *args, **kwargs):
                try:
                    return fn(self, *args, **kwargs)
                except SkypeApiException as e:
                    if isinstance(e.args[1], requests.Response) and e.args[1].status_code in codes:
                        conn = self if isinstance(self, SkypeConnection) else self.conn
                        if regToken:
                            conn.getRegToken()
                        if subscribe:
                            conn.endpoints[subscribe].subscribe()
                        return fn(self, *args, **kwargs)
                    raise
            return wrapper

        return decorator

    @classmethod
    def externalCall(cls, method, url, codes=(200, 201, 204, 207), **kwargs):
        """
        Make a public API call without a connected :class:`.Skype` instance.

        The obvious implications are that no authenticated calls are possible, though this allows accessing some public
        APIs such as join URL lookups.

        Args:
            method (str): HTTP request method
            url (str): full URL to connect to
            codes (int list): expected HTTP response codes for success
            kwargs (dict): any extra parameters to pass to :func:`requests.request`

        Returns:
            requests.Response: response object provided by :mod:`requests`

        Raises:
            SkypeAuthException: if an authentication rate limit is reached
            .SkypeApiException: if a successful status code is not received
        """
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("<= [{0}] {1} {2}".format(datetime.now().strftime("%d/%m %H:%M:%S"), method, url))
            print(pformat(kwargs))
        resp = cls.extSess.request(method, url, **kwargs)
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("=> [{0}] {1}".format(datetime.now().strftime("%d/%m %H:%M:%S"), resp.status_code))
            try:
                print(pformat(resp.json()))
            except:
                print(resp.text)
        if resp.status_code not in codes:
            raise SkypeApiException("{0} response from {1} {2}".format(resp.status_code, method, url), resp)
        return resp

    API_LOGIN = "https://login.skype.com/login"
    API_MSACC = "https://login.live.com"
    API_USER = "https://api.skype.com"
    API_JOIN = "https://join.skype.com"
    API_BOT = "https://api.aps.skype.com/v1"
    API_FLAGS = "https://flagsapi.skype.com/flags/v1"
    API_ENTITLEMENT = "https://consumer.entitlement.skype.com"
    API_SCHEDULE = "https://api.scheduler.skype.com"
    API_TRANSLATE = "https://dev.microsofttranslator.com/api"
    API_URL = "https://urlp.asm.skype.com/v1/url/info"
    API_CONTACTS = "https://contacts.skype.com/contacts/v2"
    API_MSGSHOST = "https://client-s.gateway.messenger.live.com/v1"
    API_PEOPLE = "https://people.directory.live.com/people/account/settings"
    API_DIRECTORY = "https://skypegraph.skype.com/search/v1.1/namesearch/swx/"
    API_PROFILE = "https://pf.directory.live.com/profile/mine/System.ShortCircuitProfile.json"
    # Version doesn't seem to be important, at least not for what we need.
    API_CONFIG = "https://a.config.skype.com/config/v1"

    attrs = ("userId", "tokenFile", "connected", "guest")

    extSess = requests.session()

    def __init__(self):
        """
        Create a new, unconnected instance.
        """
        self.userId = None
        self.tokens = {}
        self.tokenExpiry = {}
        self.tokenFile = None
        self.msgsHost = self.API_MSGSHOST
        self.sess = requests.Session()
        self.endpoints = {"self": SkypeEndpoint(self, "SELF")}
        self.syncStates = {}

    @property
    def connected(self):
        return "skype" in self.tokenExpiry and datetime.now() <= self.tokenExpiry["skype"] \
               and "reg" in self.tokenExpiry and datetime.now() <= self.tokenExpiry["reg"]

    @property
    def guest(self):
        return self.userId.startswith("guest:") if self.userId else None

    def __call__(self, method, url, codes=(200, 201, 204, 207), auth=None, headers=None, **kwargs):
        """
        Make an API call.  Most parameters are passed directly to :mod:`requests`.

        Set codes to a list of valid HTTP response codes -- an exception is raised if the response does not match.

        If authentication is required, set ``auth`` to one of the :class:`Auth` constants.

        Args:
            method (str): HTTP request method
            url (str): full URL to connect to
            codes (int list): expected HTTP response codes for success
            auth (Auth): authentication type to be included
            headers (dict): additional headers to be included
            kwargs (dict): any extra parameters to pass to :func:`requests.request`

        Returns:
            requests.Response: response object provided by :mod:`requests`

        Raises:
            SkypeAuthException: if an authentication rate limit is reached
            .SkypeApiException: if a successful status code is not received
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
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("<= [{0}] {1} {2}".format(datetime.now().strftime("%d/%m %H:%M:%S"), method, url))
            print(pformat(kwargs))
        resp = self.sess.request(method, url, headers=headers, **kwargs)
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("=> [{0}] {1}".format(datetime.now().strftime("%d/%m %H:%M:%S"), resp.status_code))
            try:
                print(pformat(resp.json()))
            except:
                print(resp.text)
        if resp.status_code not in codes:
            if resp.status_code == 429:
                raise SkypeAuthException("Auth rate limit exceeded", resp)
            raise SkypeApiException("{0} response from {1} {2}".format(resp.status_code, method, url), resp)
        return resp

    def syncStateCall(self, method, url, params={}, **kwargs):
        """
        Follow and track sync state URLs provided by an API endpoint, in order to implicitly handle pagination.

        In the first call, ``url`` and ``params`` are used as-is.  If a ``syncState`` endpoint is provided in the
        response, subsequent calls go to the latest URL instead.

        Args:
            method (str): HTTP request method
            url (str): full URL to connect to
            params (dict): query parameters to include in the URL
            kwargs (dict): any extra parameters to pass to :meth:`__call__`
        """
        try:
            states = self.syncStates[(method, url)]
        except KeyError:
            states = self.syncStates[(method, url)] = []
        if states:
            # We have a state link, use it to replace the URL and query string.
            url = states[-1]
            params = {}
        resp = self(method, url, params=params, **kwargs)
        try:
            json = resp.json()
        except:
            # Don't do anything if not a JSON response.
            pass
        else:
            # If a state link exists in the response, store it for later.
            state = json.get("_metadata", {}).get("syncState")
            if state:
                states.append(state)
        return resp

    def setUserPwd(self, user, pwd):
        """
        Replace the stub :meth:`getSkypeToken` method with one that connects via the Microsoft account flow using the
        given credentials.  Avoids storing the account password in an accessible way.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account
        """
        def getSkypeToken(self):
            self.liveLogin(user, pwd)
        self.getSkypeToken = MethodType(getSkypeToken, self)

    def setTokenFile(self, path):
        """
        Enable reading and writing session tokens to a file at the given location.

        Args:
            path (str): path to file used for token storage
        """
        self.tokenFile = path

    def readToken(self):
        """
        Attempt to re-establish a connection using previously acquired tokens.

        If the Skype token is valid but the registration token is invalid, a new endpoint will be registered.

        Raises:
            SkypeAuthException: if the token file cannot be used to authenticate
        """
        if not self.tokenFile:
            raise SkypeAuthException("No token file specified")
        with open(self.tokenFile, "r") as f:
            lines = f.read().splitlines()
        try:
            user, skypeToken, skypeExpiry, regToken, regExpiry, msgsHost = lines
            skypeExpiry = datetime.fromtimestamp(int(skypeExpiry))
            regExpiry = datetime.fromtimestamp(int(regExpiry))
        except:
            raise SkypeAuthException("Token file is malformed")
        if datetime.now() >= skypeExpiry:
            raise SkypeAuthException("Token file has expired")
        self.userId = user
        self.tokens["skype"] = skypeToken
        self.tokenExpiry["skype"] = skypeExpiry
        if datetime.now() < regExpiry:
            self.tokens["reg"] = regToken
            self.tokenExpiry["reg"] = regExpiry
            self.msgsHost = msgsHost
        else:
            self.getRegToken()

    def writeToken(self):
        """
        Store details of the current connection in the named file.

        This can be used by :meth:`readToken` to re-authenticate at a later time.
        """
        # Write token file privately.
        with os.fdopen(os.open(self.tokenFile, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
            f.write(self.userId + "\n")
            f.write(self.tokens["skype"] + "\n")
            f.write(str(int(time.mktime(self.tokenExpiry["skype"].timetuple()))) + "\n")
            f.write(self.tokens["reg"] + "\n")
            f.write(str(int(time.mktime(self.tokenExpiry["reg"].timetuple()))) + "\n")
            f.write(self.msgsHost + "\n")

    def verifyToken(self, auth):
        """
        Ensure the authentication token for the given auth method is still valid.

        Args:
            auth (Auth): authentication type to check

        Raises:
            SkypeAuthException: if Skype auth is required, and the current token has expired and can't be renewed
        """
        if auth in (self.Auth.SkypeToken, self.Auth.Authorize):
            if "skype" not in self.tokenExpiry or datetime.now() >= self.tokenExpiry["skype"]:
                if not hasattr(self, "getSkypeToken"):
                    raise SkypeAuthException("Skype token expired, and no password specified")
                self.getSkypeToken()
        elif auth == self.Auth.RegToken:
            if "reg" not in self.tokenExpiry or datetime.now() >= self.tokenExpiry["reg"]:
                self.getRegToken()

    def liveLogin(self, user, pwd):
        """
        Obtain connection parameters from the Microsoft account login page, and perform a login with the given email
        address or Skype username, and its password.  This emulates a login to Skype for Web on ``login.live.com``.

        .. note:: Microsoft accounts with two-factor authentication enabled are not supported.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account

        Raises:
            SkypeAuthException: if a captcha is required, or the login fails
            .SkypeApiException: if the login form can't be processed
        """
        # First, start a Microsoft account login from Skype, which will redirect to login.live.com.
        loginResp = self("GET", "{0}/oauth/microsoft".format(self.API_LOGIN),
                         params={"client_id": "578134", "redirect_uri": "https://web.skype.com"})
        # This is inside some embedded JavaScript, so can't easily parse with BeautifulSoup.
        ppft = re.search(r"""<input.*?name="PPFT".*?value="(.*?)\"""", loginResp.text).group(1)
        # Now pass the login credentials over.
        loginResp = self("POST", "{0}/ppsecure/post.srf".format(self.API_MSACC),
                         params={"wa": "wsignin1.0", "wp": "MBI_SSL",
                                 "wreply": "https://lw.skype.com/login/oauth/proxy?client_id=578134&site_name="
                                           "lw.skype.com&redirect_uri=https%3A%2F%2Fweb.skype.com%2F"},
                         cookies={"MSPRequ": loginResp.cookies.get("MSPRequ"),
                                  "MSPOK": loginResp.cookies.get("MSPOK"),
                                  "CkTst": str(int(time.time() * 1000))},
                         data={"login": user, "passwd": pwd, "PPFT": ppft})
        tField = BeautifulSoup(loginResp.text, "html.parser").find(id="t")
        if tField is None:
            if "{0}/GetSessionState.srf".format(self.API_MSACC) in loginResp.text:
                # Two-factor authentication, not supported as it's rather unwieldy to implement.
                raise SkypeAuthException("Two-factor authentication not supported", loginResp)
            err = re.search(r"sErrTxt:'([^'\\]*(\\.[^'\\]*)*)'", loginResp.text)
            if err:
                raise SkypeAuthException(err.group(1), loginResp)
        # Now exchange the 't' value for a Skype token.
        loginResp = self("POST", "{0}/microsoft".format(self.API_LOGIN),
                         params={"client_id": "578134", "redirect_uri": "https://web.skype.com"},
                         data={"t": tField.get("value"), "client_id": "578134", "oauthPartner": "999",
                               "site_name": "lw.skype.com", "redirect_uri": "https://web.skype.com"})
        loginPage = BeautifulSoup(loginResp.text, "html.parser")
        tokenField = loginPage.find("input", {"name": "skypetoken"})
        if not tokenField:
            raise SkypeApiException("Couldn't retrieve Skype token from login response", loginResp)
        self.tokens["skype"] = tokenField.get("value")
        expiryField = loginPage.find("input", {"name": "expires_in"})
        if expiryField:
            secs = int(time.time())
            self.tokenExpiry["skype"] = datetime.fromtimestamp(secs + int(expiryField.get("value")))
        # Figure out what the username is.
        self.userId = self("GET", "{0}/users/self/profile".format(self.API_USER),
                           auth=self.Auth.SkypeToken).json().get("username")
        # (Re)generate the registration token.
        self.tokens.pop("reg", None)
        self.tokenExpiry.pop("reg", None)
        self.getRegToken()

    def guestLogin(self, url, name):
        """
        Connect to Skype as a guest, joining a given conversation.

        In this state, some APIs (such as contacts) will return 401 status codes.  A guest can only communicate with
        the conversation they originally joined.

        Args:
            url (str): public join URL for conversation, or identifier from it
            name (str): display name as shown to other participants
        """
        urlId = url.split("/")[-1]
        # Pretend to be Chrome on Windows (required to avoid "unsupported device" messages).
        agent = "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) " \
                "Chrome/33.0.1750.117 Safari/537.36"
        cookies = self("GET", "{0}/{1}".format(self.API_JOIN, urlId), headers={"User-Agent": agent}).cookies
        ids = self("POST", "{0}/api/v2/conversation/".format(self.API_JOIN),
                   json={"shortId": urlId, "type": "wl"}).json()
        self.tokens["skype"] = self("POST", "{0}/api/v1/users/guests".format(self.API_JOIN),
                                    headers={"csrf_token": cookies.get("csrf_token"),
                                             "X-Skype-Request-Id": cookies.get("launcher_session_id")},
                                    json={"flowId": cookies.get("launcher_session_id"),
                                          "shortId": urlId,
                                          "longId": ids.get("Long"),
                                          "threadId": ids.get("Resource"),
                                          "name": name}).json().get("skypetoken")
        # Assume the token lasts 24 hours, as a guest account only lasts that long anyway.
        self.tokenExpiry["skype"] = datetime.now() + timedelta(days=1)
        self.userId = self("GET", "{0}/users/self/profile".format(self.API_USER),
                           auth=self.Auth.SkypeToken).json().get("username")
        self.getRegToken()

    def getSkypeToken(self):
        """
        A wrapper for :meth:`login` or :meth:`liveLogin` that applies the previously given username and password.

        Raises:
            SkypeAuthException: if credentials were never provided
        """
        raise SkypeAuthException("No username or password provided, and no valid token file")

    def getRegToken(self):
        """
        Acquire a registration token.  See :meth:`getMac256Hash` for the hash generation.

        Once successful, all tokens and expiry times are written to the token file (if specified on initialisation).
        """
        self.verifyToken(self.Auth.SkypeToken)
        self.tokens.pop("reg", None)
        self.tokenExpiry.pop("reg", None)
        while "reg" not in self.tokens:
            secs = int(time.time())
            hash = getMac256Hash(str(secs), "msmsgs@msnmsgr.com", "Q1P7W2E4J9R8U3S5")
            headers = {"LockAndKey": "appId=msmsgs@msnmsgr.com; time={0}; lockAndKeyResponse={1}".format(secs, hash),
                       "Authentication": "skypetoken=" + self.tokens["skype"]}
            endpointResp = self("POST", "{0}/users/ME/endpoints".format(self.msgsHost), codes=(200, 201, 404),
                                headers=headers, json={"endpointFeatures": "Agent"})
            regTokenHead = endpointResp.headers.get("Set-RegistrationToken")
            locHead = endpointResp.headers.get("Location")
            if regTokenHead:
                self.tokens["reg"] = re.search(r"(registrationToken=[a-z0-9\+/=]+)", regTokenHead, re.I).group(1)
                regExpiry = re.search(r"expires=(\d+)", regTokenHead).group(1)
                self.tokenExpiry["reg"] = datetime.fromtimestamp(int(regExpiry))
                regEndMatch = re.search(r"endpointId=({[a-z0-9\-]+})", regTokenHead)
                if regEndMatch:
                    self.endpoints["main"] = SkypeEndpoint(self, regEndMatch.group(1))
            if locHead:
                locParts = re.search(r"(https://[^/]+/v1)/users/ME/endpoints(/(%7B[a-z0-9\-]+%7D))?", locHead).groups()
                if not locParts[0] == self.msgsHost:
                    # Skype is requiring the use of a different hostname.
                    self.msgsHost = locHead.rsplit("/", 4 if locParts[2] else 3)[0]
                if locParts[2]:
                    self.endpoints["main"] = SkypeEndpoint(self, locParts[2].replace("%7B", "{").replace("%7D", "}"))
            if endpointResp.status_code == 200 and "main" not in self.endpoints and endpointResp.json():
                # Use the most recent endpoint listed in the JSON response.
                self.endpoints["main"] = SkypeEndpoint(self, endpointResp.json()[0]["id"])
        if "main" in self.endpoints:
            self.endpoints["main"].config()
            self.syncEndpoints()
        if self.tokenFile:
            self.writeToken()

    def syncEndpoints(self):
        """
        Retrieve all current endpoints for the connected user.
        """
        self.endpoints["all"] = []
        for json in self("GET", "{0}/users/ME/presenceDocs/messagingService".format(self.msgsHost),
                         params={"view": "expanded"}, auth=self.Auth.RegToken).json().get("endpointPresenceDocs", []):
            id = json.get("link", "").split("/")[7]
            self.endpoints["all"].append(SkypeEndpoint(self, id))


class SkypeEndpoint(SkypeObj):
    """
    An endpoint represents a single point of presence within Skype.

    Typically, a user with multiple devices would have one endpoint per device (desktop, laptop, mobile and so on).

    Endpoints are time-sensitive -- they lapse after a short time unless kept alive (by :meth:`ping` or otherwise).
    """

    attrs = ("id",)

    def __init__(self, conn, id):
        """
        Create a new instance based on a newly-created endpoint identifier.

        Args:
            conn (SkypeConnection): parent connection instance
            id (str): endpoint identifier as generated by the API
        """
        super(SkypeEndpoint, self).__init__()
        self.conn = conn
        self.id = id
        self.subscribed = False

    def config(self, name="skype"):
        """
        Configure this endpoint to allow setting presence.

        Args:
            name (str): display name for this endpoint
        """
        self.conn("PUT", "{0}/users/ME/endpoints/{1}/presenceDocs/messagingService"
                         .format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken,
                  json={"id": "messagingService",
                        "type": "EndpointPresenceDoc",
                        "selfLink": "uri",
                        "privateInfo": {"epname": name},
                        "publicInfo": {"capabilities": "",
                                       "type": 1,
                                       "skypeNameVersion": "skype.com",
                                       "nodeInfo": "xx",
                                       "version": "908/1.30.0.128"}})

    def ping(self, timeout=12):
        """
        Send a keep-alive request for the endpoint.

        Args:
            timeout (int): maximum amount of time for the endpoint to stay active
        """
        self.conn("POST", "{0}/users/ME/endpoints/{1}/active".format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken, json={"timeout": timeout})

    def subscribe(self):
        """
        Subscribe to contact and conversation events.  These are accessible through :meth:`getEvents`.
        """
        self.conn("POST", "{0}/users/ME/endpoints/{1}/subscriptions".format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken,
                  json={"interestedResources": ["/v1/threads/ALL",
                                                "/v1/users/ME/contacts/ALL",
                                                "/v1/users/ME/conversations/ALL/messages",
                                                "/v1/users/ME/conversations/ALL/properties"],
                        "template": "raw",
                        "channelType": "httpLongPoll"})
        self.subscribed = True

    def getEvents(self):
        """
        Retrieve a list of events since the last poll.  Multiple calls may be needed to retrieve all events.

        If no events occur, the API will block for up to 30 seconds, after which an empty list is returned.

        If any event occurs whilst blocked, it is returned immediately.

        Returns:
            :class:`.SkypeEvent` list: list of events, possibly empty
        """
        if not self.subscribed:
            self.subscribe()
        return self.conn("POST", "{0}/users/ME/endpoints/{1}/subscriptions/0/poll".format(self.conn.msgsHost, self.id),
                         auth=SkypeConnection.Auth.RegToken).json().get("eventMessages", [])


class SkypeAuthException(SkypeException):
    """
    An exception thrown when authentication cannot be completed.

    Generally this means the request should not be retried (e.g. because of an incorrect password), or it should be
    delayed (e.g. rate limits).
    """


def getMac256Hash(challenge, appId, key):
    """
    Method to generate the lock-and-key response, needed to acquire registration tokens.
    """
    clearText = challenge + appId
    clearText += "0" * (8 - len(clearText) % 8)

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

    cchClearText = len(clearText) // 4
    pClearText = []
    for i in range(cchClearText):
        pClearText = pClearText[:i] + [0] + pClearText[i:]
        for pos in range(4):
            pClearText[i] += ord(clearText[4 * i + pos]) * (256 ** pos)
    sha256Hash = [0, 0, 0, 0]
    hash = hashlib.sha256((challenge + key).encode("utf-8")).hexdigest().upper()
    for i in range(len(sha256Hash)):
        sha256Hash[i] = 0
        for pos in range(4):
            dpos = 8 * i + pos * 2
            sha256Hash[i] += int(hash[dpos:dpos + 2], 16) * (256 ** pos)
    macHash = cS64(pClearText, sha256Hash)
    macParts = [macHash[0], macHash[1], macHash[0], macHash[1]]
    return "".join(map(int32ToHexString, map(int64Xor, sha256Hash, macParts)))
