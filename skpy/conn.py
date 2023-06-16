import base64
import functools
import hashlib
import os
import re
import time
from datetime import datetime, timedelta
from pprint import pformat
from types import MethodType
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from .core import SkypeApiException, SkypeAuthException, SkypeEnum, SkypeObj


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
            .SkypeAuthException: if an authentication rate limit is reached
            .SkypeApiException: if a successful status code is not received
        """
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("<= [{0}] {1} {2}".format(datetime.now().strftime("%d/%m %H:%M:%S"), method, url))
            print(pformat(kwargs))
        resp = cls.extSess.request(method, url, **kwargs)
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("=> [{0}] {1}".format(datetime.now().strftime("%d/%m %H:%M:%S"), resp.status_code))
            print(pformat(dict(resp.headers)))
            try:
                print(pformat(resp.json()))
            except ValueError:
                print(resp.text)
        if resp.status_code not in codes:
            raise SkypeApiException("{0} response from {1} {2}".format(resp.status_code, method, url), resp)
        return resp

    API_LOGIN = "https://login.skype.com/login"
    API_MSACC = "https://login.live.com"
    API_EDGE = "https://edge.skype.com/rps/v1/rps/skypetoken"
    API_USER = "https://api.skype.com"
    API_AVATAR = "https://avatar.skype.com"
    API_PROFILE = "https://profile.skype.com/profile/v1"
    API_OPTIONS = "https://options.skype.com/options/v1/users/self/options"
    API_JOIN = "https://join.skype.com"
    API_JOIN_CREATE = "https://api.join.skype.com/v1"
    API_BOT = "https://api.aps.skype.com/v1"
    API_FLAGS = "https://flagsapi.skype.com/flags/v1"
    API_ENTITLEMENT = "https://consumer.entitlement.skype.com"
    API_TRANSLATE = "https://dev.microsofttranslator.com/api"
    API_ASM = "https://api.asm.skype.com/v1/objects"
    API_ASM_LOCAL = "https://{0}1-api.asm.skype.com/v1/objects"
    API_URL = "https://urlp.asm.skype.com/v1/url/info"
    API_CONTACTS = "https://contacts.skype.com/contacts/v2"
    API_MSGSHOST = "https://client-s.gateway.messenger.live.com/v1"
    API_DIRECTORY = "https://skypegraph.skype.com/v2.0/search/"
    # Version doesn't seem to be important, at least not for what we need.
    API_CONFIG = "https://a.config.skype.com/config/v1"

    USER_AGENT = "SkPy"
    USER_AGENT_BROWSER = ("Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/33.0.1750.117 Safari/537.36")
    SKYPE_CLIENT = "1418/9.99.0.999"

    attrs = ("userId", "tokenFile", "connected", "guest")

    extSess = requests.Session()
    extSess.headers["User-Agent"] = USER_AGENT

    def __init__(self):
        """
        Create a new, unconnected instance.
        """
        self.userId = None
        self.tokens = {}
        self.tokenExpiry = {}
        self.tokenFile = None
        self.hasUserPwd = False
        self.msgsHost = self.API_MSGSHOST
        self.sess = requests.Session()
        self.sess.headers["User-Agent"] = self.USER_AGENT
        self.endpoints = {"self": SkypeEndpoint(self, "SELF")}
        self.syncStates = {}

    @property
    def connected(self):
        return "skype" in self.tokenExpiry and datetime.now() <= self.tokenExpiry["skype"] \
               and "reg" in self.tokenExpiry and datetime.now() <= self.tokenExpiry["reg"]

    @property
    def guest(self):
        return self.userId.startswith("guest:") if self.userId else None

    def closure(self, method, *args, **kwargs):
        """
        Create a generic closure to call a method with fixed arguments.

        Args:
            method (MethodType): bound method of the class
            args (list): positional arguments for the method
            kwargs (dict): keyword arguments for the method

        Returns:
            MethodType: bound method closure
        """
        @functools.wraps(method)
        def inner(self):
            return method(*args, **kwargs)
        return MethodType(inner, self)

    def __call__(self, method, url, codes=(200, 201, 202, 204, 207), auth=None, headers=None, **kwargs):
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
            .SkypeAuthException: if an authentication rate limit is reached
            .SkypeApiException: if a successful status code is not received
        """
        self.verifyToken(auth)
        if not headers:
            headers = {}
        debugHeaders = dict(headers)
        if auth == self.Auth.SkypeToken:
            headers["X-SkypeToken"] = self.tokens["skype"]
            debugHeaders["X-SkypeToken"] = "***"
        elif auth == self.Auth.Authorize:
            headers["Authorization"] = "skype_token {0}".format(self.tokens["skype"])
            debugHeaders["Authorization"] = "***"
        elif auth == self.Auth.RegToken:
            headers["RegistrationToken"] = self.tokens["reg"]
            debugHeaders["RegistrationToken"] = "***"
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("<= [{0}] {1} {2}".format(datetime.now().strftime("%d/%m %H:%M:%S"), method, url))
            print(pformat(dict(kwargs, headers=debugHeaders)))
        resp = self.sess.request(method, url, headers=headers, **kwargs)
        if os.getenv("SKPY_DEBUG_HTTP"):
            print("=> [{0}] {1}".format(datetime.now().strftime("%d/%m %H:%M:%S"), resp.status_code))
            print(pformat(dict(resp.headers)))
            try:
                print(pformat(resp.json()))
            except ValueError:
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
        except ValueError:
            # Don't do anything if not a JSON response.
            pass
        else:
            # If a state link exists in the response, store it for later.
            state = json.get("_metadata", {}).get("syncState")
            if state:
                states.append(state)
        return resp

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
            .SkypeAuthException: if the token file cannot be used to authenticate
        """
        if not self.tokenFile:
            raise SkypeAuthException("No token file specified")
        try:
            with open(self.tokenFile, "r") as f:
                lines = f.read().splitlines()
        except OSError:
            raise SkypeAuthException("Token file doesn't exist or not readable")
        try:
            user, skypeToken, skypeExpiry, regToken, regExpiry, msgsHost = lines
            skypeExpiry = datetime.fromtimestamp(int(skypeExpiry))
            regExpiry = datetime.fromtimestamp(int(regExpiry))
        except ValueError:
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
            # When opening files via os, truncation must be done manually.
            f.truncate()
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
            .SkypeAuthException: if Skype auth is required, and the current token has expired and can't be renewed
        """
        if auth in (self.Auth.SkypeToken, self.Auth.Authorize):
            if "skype" not in self.tokenExpiry or datetime.now() >= self.tokenExpiry["skype"]:
                if not hasattr(self, "getSkypeToken"):
                    raise SkypeAuthException("Skype token expired, and no password specified")
                self.getSkypeToken()
        elif auth == self.Auth.RegToken:
            if "reg" not in self.tokenExpiry or datetime.now() >= self.tokenExpiry["reg"]:
                self.getRegToken()

    def skypeTokenClosure(self, method, *args, **kwargs):
        """
        Replace the stub :meth:`getSkypeToken` method with one that connects using the given credentials.  Avoids
        storing the account password in an accessible way.
        """
        self.getSkypeToken = self.closure(method, *args, **kwargs)
        self.hasUserPwd = True

    def setUserPwd(self, user, pwd):
        """
        Replace the stub :meth:`getSkypeToken` method with one that connects via SOAP login using the given
        credentials.  Avoids storing the account password in an accessible way.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account
        """
        login = self.soapLogin if "@" in user else self.liveLogin
        self.skypeTokenClosure(login, user, pwd)

    def liveLogin(self, user, pwd):
        """
        Obtain connection parameters from the Microsoft account login page, and perform a login with the given email
        address or Skype username, and its password.  This emulates a login to Skype for Web on ``login.live.com``.

        .. note::
            Microsoft accounts with two-factor authentication enabled are not supported, and will cause a
            :class:`.SkypeAuthException` to be raised.  See the exception definitions for other possible causes.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        if not self.hasUserPwd:
            self.skypeTokenClosure(self.liveLogin, user, pwd)
        self.tokens["skype"], self.tokenExpiry["skype"] = SkypeLiveAuthProvider(self).auth(user, pwd)
        self.getUserId()
        self.getRegToken()

    def soapLogin(self, user, pwd):
        """
        Perform a login with the given email address or Skype username, and its password, using the Microsoft account
        SOAP login APIs.

        .. note::
            Microsoft accounts with two-factor authentication enabled are supported if an application-specific password
            is provided.  Skype accounts must be linked to a Microsoft account with an email address, otherwise
            :class:`.SkypeAuthException` will be raised.  See the exception definitions for other possible causes.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        if not self.hasUserPwd:
            self.skypeTokenClosure(self.soapLogin, user, pwd)
        self.tokens["skype"], self.tokenExpiry["skype"] = SkypeSOAPAuthProvider(self).auth(user, pwd)
        self.getUserId()
        self.getRegToken()

    def guestLogin(self, url, name):
        """
        Connect to Skype as a guest, joining a given conversation.

        In this state, some APIs (such as contacts) will return 401 status codes.  A guest can only communicate with
        the conversation they originally joined.

        Args:
            url (str): public join URL for conversation, or identifier from it
            name (str): display name as shown to other participants

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        self.tokens["skype"], self.tokenExpiry["skype"] = SkypeGuestAuthProvider(self).auth(url, name)
        self.getUserId()
        self.getRegToken()

    def getSkypeToken(self):
        """
        A wrapper for the default login provider that applies the previously given username and password.

        Raises:
            .SkypeAuthException: if credentials were never provided
        """
        raise SkypeAuthException("No username or password provided, and no valid token file")

    def refreshSkypeToken(self):
        """
        Take the existing Skype token and refresh it, to extend the expiry time without other credentials.

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        self.tokens["skype"], self.tokenExpiry["skype"] = SkypeRefreshAuthProvider(self).auth(self.tokens["skype"])
        self.getRegToken()

    def getUserId(self):
        """
        Ask Skype for the authenticated user's identifier, and store it on the connection object.
        """
        self.userId = self("GET", "{0}/users/self/profile".format(self.API_USER),
                           auth=self.Auth.SkypeToken).json().get("username")

    def getRegToken(self):
        """
        Acquire a new registration token.

        Once successful, all tokens and expiry times are written to the token file (if specified on initialisation).
        """
        self.verifyToken(self.Auth.SkypeToken)
        token, expiry, msgsHost, endpoint = SkypeRegistrationTokenProvider(self).auth(self.tokens["skype"])
        self.tokens["reg"] = token
        self.tokenExpiry["reg"] = expiry
        self.msgsHost = msgsHost
        if endpoint:
            endpoint.config()
            self.endpoints["main"] = endpoint
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


class SkypeAuthProvider(SkypeObj):
    """
    A base class for authentication providers.  Subclasses should implement the :meth:`auth` method.
    """

    def __init__(self, conn):
        self.conn = conn

    def auth(self, *args, **kwargs):
        """
        Authenticate a user, given some form of identification.

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login forms can't be processed
        """
        raise NotImplementedError


class SkypeAPIAuthProvider(SkypeAuthProvider):
    """
    An authentication provider that connects via the Skype API.  Only compatible with Skype usernames.
    """

    def auth(self, user, pwd):
        """
        Perform a login with the given Skype username and its password.  This emulates a login to Skype for Web on
        ``api.skype.com``.

        Args:
            user (str): username of the connecting account
            pwd (str): password of the connecting account

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        # Wrap up the credentials ready to send.
        pwdHash = base64.b64encode(hashlib.md5((user + "\nskyper\n" + pwd).encode("utf-8")).digest()).decode("utf-8")
        json = self.conn("POST", "{0}/login/skypetoken".format(SkypeConnection.API_USER),
                         json={"username": user, "passwordHash": pwdHash, "scopes": "client"}).json()
        if "skypetoken" not in json:
            raise SkypeAuthException("Couldn't retrieve Skype token from response")
        expiry = None
        if "expiresIn" in json:
            expiry = datetime.fromtimestamp(int(time.time()) + int(json["expiresIn"]))
        return json["skypetoken"], expiry


class LiveAuthSuccess(Exception):
    """
    An exception used to capture the 't' value needed during Microsoft account authentication.
    """

    def __init__(self, t):
        super(LiveAuthSuccess, self).__init__(t)
        self.t = t


class SkypeLiveAuthProvider(SkypeAuthProvider):
    """
    An authentication provider that connects via Microsoft account authentication.
    """

    def checkUser(self, user):
        """
        Query a username or email address to see if a corresponding Microsoft account exists.

        Args:
            user (str): username or email address of an account

        Returns:
            bool: whether the account exists
        """
        return not self.conn("POST", "{0}/GetCredentialType.srf".format(SkypeConnection.API_MSACC),
                             json={"username": user}).json().get("IfExistsResult")

    def auth(self, user, pwd):
        """
        Obtain connection parameters from the Microsoft account login page, and perform a login with the given email
        address or Skype username, and its password.  This emulates a login to Skype for Web on ``login.live.com``.

        .. note::
            Microsoft accounts with two-factor authentication enabled are not supported, and will cause a
            :class:`.SkypeAuthException` to be raised.  See the exception definitions for other possible causes.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        try:
            self.getT(user, pwd)
        except LiveAuthSuccess as ex:
            return self.getToken(ex.t)

    def check(self, resp):
        page = BeautifulSoup(resp.text, "html.parser")
        # Look for the 't' value we need to exchange for a Skype token, which might turn up at any stage.
        tField = page.find(id="t")
        if tField is not None:
            raise LiveAuthSuccess(tField.get("value"))
        # Look for an error message within the response.
        errReg = re.search(r"sErrTxt:'([^'\\]*(\\.[^'\\]*)+)'", resp.text)
        if errReg:
            errMsg = re.sub(r"<.*?>", "", errReg.group(1)).replace("\\'", "'").replace("\\\\", "\\")
            raise SkypeApiException(errMsg, resp)
        # Look for two-factor authentication device information (a non-empty array of factors) that we can't handle.
        if re.search(r"\bV:\s*\[\s*{", resp.text):
            raise SkypeAuthException("Two-factor authentication unsupported", resp)
        # Look for a user consent form, meaning the user needs to accept terms or follow account security steps.
        for form in page.findAll("form"):
            if form["name"] == "fmHF":
                url = form["action"].split("?", 1)[0]
                raise SkypeAuthException("Account action required ({0}), login with a web browser first"
                                         .format(url), resp)
        # No common elements, return the response for further processing.
        return resp

    def getT(self, user, pwd):
        # Stage 1: Start a Microsoft account login from Skype, which will redirect to login.live.com.
        stage1Resp = self.check(self.conn("GET", "{0}/oauth/microsoft".format(SkypeConnection.API_LOGIN),
                                          params={"client_id": "578134", "redirect_uri": "https://web.skype.com"}))
        # This is inside some embedded JavaScript, so can't easily parse with BeautifulSoup.
        ppftReg = re.search(r"""<input.*?name="PPFT".*?value="(.*?)""" + "\"", stage1Resp.text)
        if not ppftReg:
            raise SkypeApiException("Couldn't retrieve PPFT from login form", stage1Resp)
        ppft = ppftReg.group(1)
        if "MSPRequ" not in stage1Resp.cookies or "MSPOK" not in stage1Resp.cookies:
            raise SkypeApiException("Couldn't retrieve MSPRequ/MSPOK cookies", stage1Resp)
        # Prepare the Live login page request parameters.
        params = {"wa": "wsignin1.0", "wp": "MBI_SSL",
                  "wreply": "https://lw.skype.com/login/oauth/proxy?client_id=578134&site_name="
                            "lw.skype.com&redirect_uri=https%3A%2F%2Fweb.skype.com%2F"}
        cookies = {"MSPRequ": stage1Resp.cookies.get("MSPRequ"), "MSPOK": stage1Resp.cookies.get("MSPOK")}
        # Stage 2: Submit the user's credentials.
        stage2Resp = self.check(self.conn("POST", "{0}/ppsecure/post.srf".format(SkypeConnection.API_MSACC),
                                          params=params,
                                          cookies=dict(cookies, CkTst="G{0}".format(int(time.time() * 1000))),
                                          data={"login": user, "passwd": pwd, "PPFT": ppft, "loginoptions": "3"}))
        opidReg = re.search(r"""opid=([A-Z0-9]+)""", stage2Resp.text, re.I)
        if not opidReg:
            raise SkypeApiException("Couldn't retrieve opid field from login response", stage2Resp)
        # Stage 3: Repeat with the 'opid' parameter.
        stage3Resp = self.check(self.conn("POST", "{0}/ppsecure/post.srf".format(SkypeConnection.API_MSACC),
                                          params=params,
                                          cookies=dict(cookies, CkTst="G{0}".format(int(time.time() * 1000))),
                                          data={"opid": opidReg.group(1), "PPFT": ppft, "site_name": "lw.skype.com",
                                                "oauthPartner": "999", "client_id": "578134",
                                                "redirect_uri": "https://web.skype.com", "type": "28"}))
        # No check matches, and no further actions we can take.
        raise SkypeApiException("Couldn't retrieve t field from login response", stage3Resp)

    def getToken(self, t):
        # Now exchange the 't' value for a Skype token.
        loginResp = self.conn("POST", "{0}/microsoft".format(SkypeConnection.API_LOGIN),
                              params={"client_id": "578134", "redirect_uri": "https://web.skype.com"},
                              data={"t": t, "client_id": "578134", "oauthPartner": "999",
                                    "site_name": "lw.skype.com", "redirect_uri": "https://web.skype.com"})
        loginPage = BeautifulSoup(loginResp.text, "html.parser")
        # Collect the Skype token, and expiry if present.
        tokenField = loginPage.find("input", {"name": "skypetoken"})
        if not tokenField:
            raise SkypeApiException("Couldn't retrieve Skype token from login response", loginResp)
        token = tokenField.get("value")
        expiryField = loginPage.find("input", {"name": "expires_in"})
        expiry = None
        if expiryField:
            expiry = datetime.fromtimestamp(int(time.time()) + int(expiryField.get("value")))
        return (token, expiry)


class SkypeSOAPAuthProvider(SkypeAuthProvider):
    """
    An authentication provider that connects via Microsoft account SOAP authentication.
    """

    template = """
    <Envelope xmlns='http://schemas.xmlsoap.org/soap/envelope/'
       xmlns:wsse='http://schemas.xmlsoap.org/ws/2003/06/secext'
       xmlns:wsp='http://schemas.xmlsoap.org/ws/2002/12/policy'
       xmlns:wsa='http://schemas.xmlsoap.org/ws/2004/03/addressing'
       xmlns:wst='http://schemas.xmlsoap.org/ws/2004/04/trust'
       xmlns:ps='http://schemas.microsoft.com/Passport/SoapServices/PPCRL'>
       <Header>
           <wsse:Security>
               <wsse:UsernameToken Id='user'>
                   <wsse:Username>{}</wsse:Username>
                   <wsse:Password>{}</wsse:Password>
               </wsse:UsernameToken>
           </wsse:Security>
       </Header>
       <Body>
           <ps:RequestMultipleSecurityTokens Id='RSTS'>
               <wst:RequestSecurityToken Id='RST0'>
                   <wst:RequestType>http://schemas.xmlsoap.org/ws/2004/04/security/trust/Issue</wst:RequestType>
                   <wsp:AppliesTo>
                       <wsa:EndpointReference>
                           <wsa:Address>wl.skype.com</wsa:Address>
                       </wsa:EndpointReference>
                   </wsp:AppliesTo>
                   <wsse:PolicyReference URI='MBI_SSL'></wsse:PolicyReference>
               </wst:RequestSecurityToken>
           </ps:RequestMultipleSecurityTokens>
       </Body>
    </Envelope>
    """

    @staticmethod
    def encode(value):
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def auth(self, user, pwd):
        """
        Perform a SOAP login with the given email address or Skype username, and its password.

        .. note::
            Microsoft accounts with two-factor authentication enabled must provide an application-specific password.

        Args:
            user (str): username or email address of the connecting account
            pwd (str): password of the connecting account

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        token = self.getSecToken(user, pwd)
        return self.exchangeToken(token)

    def getSecToken(self, user, pwd):
        loginResp = self.conn("POST", "{0}/RST.srf".format(SkypeConnection.API_MSACC),
                              data=self.template.format(self.encode(user), self.encode(pwd)))
        loginData = ElementTree.fromstring(loginResp.text)
        token = None
        for node in loginData.iter():
            tag = node.tag.split("}", 1)[-1]
            if tag == "Fault":
                code = msg = None
                for fnode in node:
                    ftag = fnode.tag.split("}", 1)[-1]
                    if ftag == "faultcode":
                        code = fnode.text
                    elif ftag == "faultstring":
                        msg = fnode.text
                if code or msg:
                    raise SkypeAuthException("{} - {}".format(code, msg), loginResp)
                else:
                    raise SkypeApiException("Unknown fault whilst requesting security token", loginResp)
            elif tag == "BinarySecurityToken":
                token = node.text
        if not token:
            raise SkypeApiException("Couldn't retrieve security token from login response", loginResp)
        return token

    def exchangeToken(self, token):
        edgeResp = self.conn("POST", SkypeConnection.API_EDGE,
                             data={"partner": 999, "access_token": token, "scopes": "client"})
        try:
            edgeData = edgeResp.json()
        except ValueError:
            raise SkypeApiException("Couldn't parse edge response body", edgeResp)
        if "skypetoken" in edgeData:
            token = edgeData["skypetoken"]
            expiry = None
            if "expiresIn" in edgeData:
                expiry = datetime.fromtimestamp(int(time.time()) + int(edgeData["expiresIn"]))
            return (token, expiry)
        elif "status" in edgeData:
            status = edgeData["status"]
            raise SkypeApiException("{} - {}".format(status.get("code"), status.get("text")), edgeResp)
        else:
            raise SkypeApiException("Couldn't retrieve token from edge response", edgeResp)


class SkypeGuestAuthProvider(SkypeAuthProvider):
    """
    An authentication provider that connects and joins a public conversation via a join URL.
    """

    def auth(self, url, name):
        """
        Connect to Skype as a guest, joining a given conversation.

        In this state, some APIs (such as contacts) will return 401 status codes.  A guest can only communicate with
        the conversation they originally joined.

        Args:
            url (str): public join URL for conversation, or identifier from it
            name (str): display name as shown to other participants

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        urlId = url.split("/")[-1]
        # Pretend to be Chrome on Windows (required to avoid "unsupported device" messages).
        cookies = self.conn("GET", "{0}/{1}".format(SkypeConnection.API_JOIN, urlId),
                            headers={"User-Agent": SkypeConnection.USER_AGENT_BROWSER}).cookies
        ids = self.conn("POST", "{0}/api/v2/conversation/".format(SkypeConnection.API_JOIN),
                        json={"shortId": urlId, "type": "wl"}).json()
        token = self.conn("POST", "{0}/api/v1/users/guests".format(SkypeConnection.API_JOIN),
                          headers={"csrf_token": cookies.get("csrf_token"),
                                   "X-Skype-Request-Id": cookies.get("launcher_session_id")},
                          json={"flowId": cookies.get("launcher_session_id"),
                                "shortId": urlId,
                                "longId": ids.get("Long"),
                                "threadId": ids.get("Resource"),
                                "name": name}).json().get("skypetoken")
        # Assume the token lasts 24 hours, as a guest account only lasts that long anyway.
        expiry = datetime.now() + timedelta(days=1)
        return token, expiry


class SkypeRefreshAuthProvider(SkypeAuthProvider):
    """
    An authentication provider that connects via the Skype API.  Only compatible with Skype usernames.
    """

    def auth(self, token):
        """
        Take an existing Skype token and refresh it, to extend the expiry time without other credentials.

        Args:
            token (str): existing Skype token

        Returns:
            (str, datetime.datetime) tuple: Skype token, and associated expiry if known

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        t = self.sendToken(token)
        return self.getToken(t)

    def sendToken(self, token):
        # Send the existing token over.
        loginResp = self.conn("GET", "{0}/login".format(SkypeConnection.API_LOGIN),
                              params={"client_id": "578134", "redirect_uri": "https://web.skype.com"},
                              cookies={"refresh-token": token})
        tField = BeautifulSoup(loginResp.text, "html.parser").find(id="t")
        if tField is None:
            err = re.search(r"sErrTxt:'([^'\\]*(\\.[^'\\]*)*)'", loginResp.text)
            errMsg = "Couldn't retrieve t field from login response"
            if err:
                errMsg = re.sub(r"<.*?>", "", err.group(1)).replace("\\'", "'").replace("\\\\", "\\")
            raise SkypeAuthException(errMsg, loginResp)
        return tField.get("value")

    def getToken(self, t):
        # Now exchange the 't' value for a Skype token.
        loginResp = self.conn("POST", "{0}/microsoft".format(SkypeConnection.API_LOGIN),
                              params={"client_id": "578134", "redirect_uri": "https://web.skype.com"},
                              data={"t": t, "client_id": "578134", "oauthPartner": "999",
                                    "site_name": "lw.skype.com", "redirect_uri": "https://web.skype.com"})
        loginPage = BeautifulSoup(loginResp.text, "html.parser")
        # Collect the Skype token, and expiry if present.
        tokenField = loginPage.find("input", {"name": "skypetoken"})
        if not tokenField:
            raise SkypeApiException("Couldn't retrieve Skype token from login response", loginResp)
        token = tokenField.get("value")
        expiryField = loginPage.find("input", {"name": "expires_in"})
        expiry = None
        if expiryField:
            expiry = datetime.fromtimestamp(int(time.time()) + int(expiryField.get("value")))
        return (token, expiry)


class SkypeRegistrationTokenProvider(SkypeAuthProvider):
    """
    An authentication provider that handles the handshake for a registration token.
    """

    def auth(self, skypeToken):
        """
        Request a new registration token using a current Skype token.

        Args:
            skypeToken (str): existing Skype token

        Returns:
            (str, datetime.datetime, str, SkypeEndpoint) tuple: registration token, associated expiry if known,
                                                                resulting endpoint hostname, endpoint if provided

        Raises:
            .SkypeAuthException: if the login request is rejected
            .SkypeApiException: if the login form can't be processed
        """
        token = expiry = endpoint = None
        msgsHost = SkypeConnection.API_MSGSHOST
        while not token:
            secs = int(time.time())
            hash = self.getMac256Hash(str(secs))
            headers = {"LockAndKey": "appId=msmsgs@msnmsgr.com; time={0}; lockAndKeyResponse={1}".format(secs, hash),
                       "Authentication": "skypetoken=" + skypeToken, "BehaviorOverride": "redirectAs404"}
            endpointResp = self.conn("POST", "{0}/users/ME/endpoints".format(msgsHost), codes=(200, 201, 404),
                                     headers=headers, json={"endpointFeatures": "Agent"})
            regTokenHead = endpointResp.headers.get("Set-RegistrationToken")
            locHead = endpointResp.headers.get("Location")
            if locHead:
                locParts = re.search(r"(https://[^/]+/v1)/users/ME/endpoints(/(%7B[a-z0-9\-]+%7D))?", locHead).groups()
                if locParts[2]:
                    endpoint = SkypeEndpoint(self.conn, locParts[2].replace("%7B", "{").replace("%7D", "}"))
                if not locParts[0] == msgsHost:
                    # Skype is requiring the use of a different hostname.
                    msgsHost = locHead.rsplit("/", 4 if locParts[2] else 3)[0]
                    # Don't accept the token if present, we need to re-register first.
                    continue
            if regTokenHead:
                token = re.search(r"(registrationToken=[a-z0-9\+/=]+)", regTokenHead, re.I).group(1)
                regExpiry = re.search(r"expires=(\d+)", regTokenHead).group(1)
                expiry = datetime.fromtimestamp(int(regExpiry))
                regEndMatch = re.search(r"endpointId=({[a-z0-9\-]+})", regTokenHead)
                if regEndMatch:
                    endpoint = SkypeEndpoint(self.conn, regEndMatch.group(1))
            if not endpoint and endpointResp.status_code == 200 and endpointResp.json():
                # Use the most recent endpoint listed in the JSON response.
                endpoint = SkypeEndpoint(self.conn, endpointResp.json()[0]["id"])
        return token, expiry, msgsHost, endpoint

    @staticmethod
    def getMac256Hash(challenge, appId="msmsgs@msnmsgr.com", key="Q1P7W2E4J9R8U3S5"):
        """
        Generate the lock-and-key response, needed to acquire registration tokens.
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


class SkypeEndpoint(SkypeObj):
    """
    An endpoint represents a single point of presence within Skype.

    Typically, a user with multiple devices would have one endpoint per device (desktop, laptop, mobile and so on).

    Endpoints are time-sensitive -- they lapse after a short time unless kept alive (by :meth:`ping` or otherwise).
    """

    attrs = ("id",)

    resources = ["/v1/users/ME/conversations/ALL/properties",
                 "/v1/users/ME/conversations/ALL/messages",
                 "/v1/threads/ALL"]

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
        self.subscribedPresence = False

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
                  json={"interestedResources": self.resources,
                        "channelType": "HttpLongPoll",
                        "conversationType": 2047})
        self.subscribed = True

    def subscribePresence(self, contacts):
        """
        Enable presence subscriptions for the authenticated user's contacts.

        Args:
            contacts (.SkypeContacts): contact list to select user IDs
        """
        if not self.subscribed:
            self.subscribe()
        resources = list(self.resources)
        for contact in contacts:
            resources.append("/v1/users/ME/contacts/8:{}".format(contact.id))
        self.conn("PUT", "{0}/users/ME/endpoints/{1}/subscriptions/0".format(self.conn.msgsHost, self.id),
                  auth=SkypeConnection.Auth.RegToken,
                  params={"name": "interestedResources"},
                  json={"interestedResources": resources})
        self.subscribedPresence = True

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
