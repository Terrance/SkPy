#!/usr/bin/env python

from datetime import datetime, timedelta
import time
import re
import unittest

from requests import Response
import responses

from skpy import Skype, SkypeConnection

class Data:
    """
    Dummy representations of data normally retrieved from Skype.
    """
    userId = "fred.2"
    skypeToken = "s" * 424
    regToken = "r" * 886
    tokenExpiry = datetime.now() + timedelta(days=1)
    msgsHost = "https://db1-client-s.gateway.messenger.live.com/v1"
    endpointId = "{eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee}"
    chatShortId = "c" * 12
    chatLongId = "c" * 32
    chatThreadId = "19:{0}@thread.skype".format(chatLongId)
    guestId = "guest:name_gggggggg"


def registerMocks(regTokenRedirect=False, guest=False):
    """
    Override external calls to Skype APIs with static responses using :mod:`responses`.

    Args:
        regTokenRedirect (bool): whether to emulate the 'user is on another cloud' host redirect
        guest (bool): whether to emulate a guest account
    """
    # Retrieve the login form.
    responses.add(responses.GET, "https://login.skype.com/login",
                  status=200, content_type="text/html",
                  body="""<html><body><input id="pie" value="pievalue">
                          <input id="etm" value="etmvalue"></body></html>""")
    # Submit username/password to form.
    responses.add(responses.POST, "https://login.skype.com/login",
                  status=200, content_type="text/html",
                  body="""<html><body><input name="skypetoken" value="{0}">
                          <input name="expires_in" value="86400"></body></html>""".format(Data.skypeToken))
    # Request registration token.
    expiry = int(time.mktime((datetime.now() + timedelta(days=1)).timetuple()))
    if regTokenRedirect:
        responses.add(responses.POST, "{0}/users/ME/endpoints".format(SkypeConnection.API_MSGSHOST), status=404,
                      adding_headers={"Location": "{0}/users/ME/endpoints".format(Data.msgsHost)})
        responses.add(responses.POST, "{0}/users/ME/endpoints".format(Data.msgsHost), status=200,
                      adding_headers={"Set-RegistrationToken": "registrationToken={0}; expires={1}; endpointId={2}"
                                                               .format(Data.regToken, expiry, Data.endpointId)})
    else:
        responses.add(responses.POST, "{0}/users/ME/endpoints".format(SkypeConnection.API_MSGSHOST), status=200,
                      adding_headers={"Set-RegistrationToken": "registrationToken={0}; expires={1}; endpointId={2}"
                                                               .format(Data.regToken, expiry, Data.endpointId)})
    # Retrieve public information about a group chat.
    responses.add(responses.GET, re.compile("{0}/[a-z0-9]{{12}}".format(SkypeConnection.API_JOIN), re.I),
                  status=200, adding_headers={"Set-Cookie": "csrf_token=csrf; launcher_session_id=launch"})
    responses.add(responses.POST, "{0}/api/v2/conversation/".format(SkypeConnection.API_JOIN),
                  status=200, content_type="application/json",
                  json={"Long": Data.chatLongId, "Resource": Data.chatThreadId})
    # Join a conversation as a guest.
    responses.add(responses.POST, "{0}/api/v1/users/guests".format(SkypeConnection.API_JOIN),
                  status=200, content_type="application/json", json={"skypetoken": Data.skypeToken})
    # Retrieve info on the current user.
    responses.add(responses.GET, "{0}/users/self/profile".format(SkypeConnection.API_USER),
                  status=200, content_type="application/json",
                  json={"username": Data.guestId if guest else Data.userId})


def mockSkype():
    """
    Create a fake, pre-connected Skype instance.
    """
    registerMocks()
    sk = Skype()
    sk.conn.userId = Data.userId
    sk.conn.tokens["skype"] = Data.skypeToken
    sk.conn.tokens["reg"] = "registrationToken={0}".format(Data.skypeToken)
    sk.conn.tokenExpiry["skype"] = sk.conn.tokenExpiry["reg"] = Data.tokenExpiry
    return sk


class SkypeTest(unittest.TestCase):
    """
    Main test class for all SkPy code.

    Each test method enables the intercepting of API calls as defined in :func:`registerMocks`.

    Note that tests should be designed to evaluate local code -- they are not testing correctness of the Skype APIs,
    rather that the local classes handle the requests and responses appropriately.
    """

    @responses.activate
    def testAuth(self):
        """
        Complete the auth flow with a dummy username and password.
        """
        registerMocks()
        sk = Skype("fred.2", "password")
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        self.assertEqual(sk.conn.msgsHost, SkypeConnection.API_MSGSHOST)
        self.assertEqual(sk.conn.endpoints["main"].id, Data.endpointId)
        self.assertTrue(sk.conn.connected)
        self.assertFalse(sk.conn.guest)
        self.assertEqual(sk.userId, Data.userId)

    @responses.activate
    def testAuthRedirect(self):
        """
        Complete the auth flow with a dummy username and password, including a messenger hostname redirect.
        """
        registerMocks(regTokenRedirect=True)
        sk = Skype("fred.2", "password")
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        self.assertEqual(sk.conn.msgsHost, Data.msgsHost)
        self.assertEqual(sk.conn.endpoints["main"].id, Data.endpointId)
        self.assertTrue(sk.conn.connected)
        self.assertFalse(sk.conn.guest)
        self.assertEqual(sk.userId, Data.userId)

    @responses.activate
    def testGuestAuth(self):
        """
        Complete the auth flow as a guest joining a conversation.
        """
        registerMocks(guest=True)
        sk = Skype()
        sk.conn.guestLogin(Data.chatShortId, "Name")
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        self.assertEqual(sk.conn.msgsHost, SkypeConnection.API_MSGSHOST)
        self.assertEqual(sk.conn.endpoints["main"].id, Data.endpointId)
        self.assertTrue(sk.conn.connected)
        self.assertTrue(sk.conn.guest)
        self.assertEqual(sk.userId, Data.guestId)


if __name__ == "__main__":
    unittest.main()
