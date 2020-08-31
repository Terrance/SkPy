#!/usr/bin/env python

from datetime import datetime, timedelta
import json
import time
import re
import unittest

from urllib3.connection import HTTPHeaderDict

import responses

from skpy import Skype, SkypeConnection, SkypeContact, SkypeMsg, SkypeTextMsg, SkypeUtils


class Data:
    """
    Dummy representations of data normally retrieved from Skype.
    """

    userId = "fred.2"
    secToken = "t={}&amp;p=".format("s" * 1048)
    skypeToken = "s" * 424
    regToken = "r" * 886
    tokenExpiry = datetime.now() + timedelta(days=1)
    msgsHost = "https://db1-client-s.gateway.messenger.live.com/v1"
    endpointId = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    chatShortId = "c" * 12
    chatLongId = "c" * 32
    chatThreadId = "19:{0}@thread.skype".format(chatLongId)
    chatP2PThreadId = "19:{0}@p2p.thread.skype".format(chatLongId)
    guestId = "guest:name_gggggggg"
    contactId = "joe.4"
    liveContactId = "live:joe.4"
    nonContactId = "anna.7"
    botContactId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    asmId = "0-weu-aa-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    msgTime = 1451606400000
    msgTimeStr = "{0}".format(msgTime)
    msgTimeFmt = "2016-01-01T00:00:00.000Z"
    msgId = "1451606399999"


def registerMocks(regTokenRedirect=False, guest=False):
    """
    Override external calls to Skype APIs with static responses using :mod:`responses`.

    Args:
        regTokenRedirect (bool): whether to emulate the 'user is on another cloud' host redirect
        guest (bool): whether to emulate a guest account
    """
    # Live login: retrieve the login form.
    responses.add(responses.GET, "{0}/oauth/microsoft".format(SkypeConnection.API_LOGIN), status=200,
                  adding_headers=HTTPHeaderDict((("Set-Cookie", "MSPRequ=MSPRequ"),
                                                 ("Set-Cookie", "MSPOK=MSPOK"))), content_type="text/html",
                  body="""<html><body><input name="PPFT" value="ppftvalue"></body></html>""")
    # Live login: submit username/password to form.
    liveBody = """<html>
      <body>
        <!-- Stage 1: opid -->
        <script type="text/javascript">
          f({urlPost:'https://login.live.com/ppsecure/post.srf?wa=wsignin1.0&opid=66AE4377820CC67F'});
        </script>
        <!-- Stage 2: t -->
        <input id="t" value="tvalue">
      </body>
    </html>"""
    responses.add(responses.POST, "{0}/ppsecure/post.srf".format(SkypeConnection.API_MSACC),
                  status=200, content_type="text/html", body=liveBody)
    responses.add(responses.POST, "{0}/microsoft".format(SkypeConnection.API_LOGIN),
                  status=200, content_type="text/html",
                  body="""<html><body><input name="skypetoken" value="{0}">
                          <input name="expires_in" value="86400"></body></html>""".format(Data.skypeToken))
    # SOAP login: submit username/password.
    secTokenBody = """<?xml version="1.0" encoding="utf-8" ?>
    <S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
        <S:Body>
            <wst:RequestSecurityTokenResponseCollection
             xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"
             xmlns:wst="http://schemas.xmlsoap.org/ws/2004/04/trust"
             xmlns:wsse="http://schemas.xmlsoap.org/ws/2003/06/secext"
             xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
             xmlns:saml="urn:oasis:names:tc:SAML:1.0:assertion"
             xmlns:wsp="http://schemas.xmlsoap.org/ws/2002/12/policy"
             xmlns:psf="http://schemas.microsoft.com/Passport/SoapServices/SOAPFault">
                <wst:RequestSecurityTokenResponse>
                    <wst:RequestedSecurityToken>
                        <wsse:BinarySecurityToken Id="Compact0">{}</wsse:BinarySecurityToken>
                    </wst:RequestedSecurityToken>
                </wst:RequestSecurityTokenResponse>
            </wst:RequestSecurityTokenResponseCollection>
        </S:Body>
    </S:Envelope>""".format(Data.secToken)
    responses.add(responses.POST, "{0}/RST.srf".format(SkypeConnection.API_MSACC),
                  status=200, content_type="text/xml", body=secTokenBody)
    # SOAP login: exchange edge token.
    responses.add(responses.POST, SkypeConnection.API_EDGE, status=200, content_type="application/json",
                  body=json.dumps({"skypetoken": Data.skypeToken, "expiresIn": 86400}))
    # Request registration token.
    expiry = int(time.mktime((datetime.now() + timedelta(days=1)).timetuple()))
    msgsHost = Data.msgsHost if regTokenRedirect else SkypeConnection.API_MSGSHOST
    if regTokenRedirect:
        responses.add(responses.POST, "{0}/users/ME/endpoints".format(SkypeConnection.API_MSGSHOST), status=404,
                      adding_headers={"Location": "{0}/users/ME/endpoints".format(Data.msgsHost)})
    responses.add(responses.POST, "{0}/users/ME/endpoints".format(msgsHost), status=200,
                  adding_headers={"Set-RegistrationToken": "registrationToken={0}; expires={1}; endpointId={{{2}}}"
                                                           .format(Data.regToken, expiry, Data.endpointId)})
    # Configure and retrieve endpoints.
    responses.add(responses.PUT, "{0}/users/ME/endpoints/%7B{1}%7D/presenceDocs/messagingService"
                                 .format(msgsHost, Data.endpointId), status=200)
    responses.add(responses.GET, "{0}/users/ME/presenceDocs/messagingService"
                                 .format(msgsHost), status=200, json={"endpointPresenceDocs": []})
    # Retrieve user flags.
    responses.add(responses.GET, SkypeConnection.API_FLAGS, status=200, json=[1])
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
    # Retrieve a list of contacts.
    responses.add(responses.GET, "{0}/users/{1}".format(SkypeConnection.API_CONTACTS, Data.userId),
                  status=200, content_type="application/json",
                  json={"contacts": [{"authorized": True,
                                      "blocked": False,
                                      "display_name": "Joe Bloggs",
                                      "mri": Data.contactId,
                                      "profile": {"avatar_url": "https://api.skype.com/users/{0}/profile/avatar"
                                                                .format(Data.contactId),
                                                  "locations": [{"city": "London", "state": None, "country": "GB"}],
                                                  "mood": "Happy <ss type=\"laugh\">:D</ss>",
                                                  "name": {"first": "Joe", "surname": "Bloggs",
                                                           "nickname": "Joe Bloggs"},
                                                  "phones": [{"number": "+442099887766", "type": 0},
                                                             {"number": "+442020900900", "type": 1},
                                                             {"number": "+447711223344", "type": 2}]}},
                                     {"authorized": False,
                                      "blocked": False,
                                      "display_name": "Anna Cooper",
                                      "id": Data.nonContactId,
                                      "name": {"first": "Anna", "surname": "Cooper"},
                                      "suggested": True}]})
    # Retrieve a list of conversations.
    userFmt = (SkypeConnection.API_MSGSHOST, Data.userId)
    conFmt = (SkypeConnection.API_MSGSHOST, Data.contactId)
    nonConFmt = (SkypeConnection.API_MSGSHOST, Data.nonContactId)
    chatFmt = (SkypeConnection.API_MSGSHOST, Data.chatThreadId)
    responses.add(responses.GET, "{0}/users/ME/conversations".format(SkypeConnection.API_MSGSHOST),
                  status=200, content_type="application/json",
                  json={"conversations": [{"id": "8:{0}".format(Data.contactId),
                                           "lastMessage": {"clientmessageid": Data.msgId,
                                                           "composetime": Data.msgTimeFmt,
                                                           "content": "Hi!",
                                                           "conversationLink": "{0}/users/ME/conversations/8:{1}"
                                                                               .format(*conFmt),
                                                           "from": "{0}/users/ME/contacts/8:{1}".format(*conFmt),
                                                           "id": Data.msgTimeStr,
                                                           "messagetype": "Text",
                                                           "originalarrivaltime": Data.msgTimeFmt,
                                                           "type": "Message",
                                                           "version": Data.msgTimeStr},
                                           "messages": "{0}/users/ME/conversations/8:{1}/messages".format(*conFmt),
                                           "properties": {"clearedat": Data.msgTimeStr,
                                                          "consumptionhorizon": "0;0;0"},
                                           "targetLink": "{0}/users/ME/contacts/8:{1}".format(*conFmt),
                                           "type": "Conversation",
                                           "version": Data.msgTime},
                                          {"id": Data.chatThreadId,
                                           "lastMessage": {"clientmessageid": Data.msgId,
                                                           "composetime": Data.msgTimeFmt,
                                                           "content": "A message for the team.",
                                                           "conversationLink": "{0}/users/ME/conversations/{1}"
                                                                               .format(*chatFmt),
                                                           "from": "{0}/users/ME/contacts/8:{1}".format(*nonConFmt),
                                                           "id": Data.msgTimeStr,
                                                           "messagetype": "Text",
                                                           "originalarrivaltime": Data.msgTimeFmt,
                                                           "type": "Message",
                                                           "version": Data.msgTimeStr},
                                           "messages": "{0}/users/ME/conversations/{1}/messages".format(*chatFmt),
                                           "properties": {"consumptionhorizon": "0;0;0"},
                                           "targetLink": "{0}/threads/{1}".format(*chatFmt),
                                           "threadProperties": {"lastjoinat": Data.msgTimeStr,
                                                                "topic": "Team chat",
                                                                "version": Data.msgTimeStr},
                                           "type": "Conversation",
                                           "version": Data.msgTime}]})
    # Retrieve a single conversation.
    responses.add(responses.GET, "{0}/users/ME/conversations/{1}".format(*chatFmt),
                  status=200, content_type="application/json",
                  json={"id": Data.chatThreadId,
                        "lastMessage": {"clientmessageid": Data.msgId,
                                        "composetime": Data.msgTimeFmt,
                                        "content": "A message for the team.",
                                        "conversationLink": "{0}/users/ME/conversations/{1}"
                                                            .format(*chatFmt),
                                        "from": "{0}/users/ME/contacts/8:{1}".format(*nonConFmt),
                                        "id": Data.msgTimeStr,
                                        "messagetype": "Text",
                                        "originalarrivaltime": Data.msgTimeFmt,
                                        "type": "Message",
                                        "version": Data.msgTimeStr},
                        "messages": "{0}/users/ME/conversations/{1}/messages".format(*chatFmt),
                        "properties": {"consumptionhorizon": "0;0;0"},
                        "targetLink": "{0}/threads/{1}".format(*chatFmt),
                        "threadProperties": {"lastjoinat": Data.msgTimeStr,
                                             "topic": "Team chat",
                                             "version": Data.msgTimeStr},
                        "type": "Conversation",
                        "version": Data.msgTime})
    # Request more information about the group conversation.
    responses.add(responses.GET, "{0}/threads/{1}".format(*chatFmt), status=200, content_type="application/json",
                  json={"id": Data.chatThreadId,
                        "members": [{"capabilities": [],
                                     "cid": 0,
                                     "friendlyName": "",
                                     "id": "8:{0}".format(Data.nonContactId),
                                     "linkedMri": "",
                                     "role": "Admin",
                                     "type": "ThreadMember",
                                     "userLink": "{0}/users/8:{1}".format(*nonConFmt),
                                     "userTile": ""},
                                    {"capabilities": [],
                                     "cid": 0,
                                     "friendlyName": "",
                                     "id": "8:{0}".format(Data.contactId),
                                     "linkedMri": "",
                                     "role": "User",
                                     "type": "ThreadMember",
                                     "userLink": "{0}/users/8:{1}".format(*conFmt),
                                     "userTile": ""},
                                    {"capabilities": [],
                                     "cid": 0,
                                     "friendlyName": "",
                                     "id": "8:{0}".format(Data.userId),
                                     "linkedMri": "",
                                     "role": "User",
                                     "type": "ThreadMember",
                                     "userLink": "{0}/users/8:{1}".format(*userFmt),
                                     "userTile": ""}],
                        "messages": "{0}/users/ME/conversations/{1}/messages".format(*chatFmt),
                        "properties": {"capabilities": ["AddMember",
                                                        "ChangeTopic",
                                                        "ChangePicture",
                                                        "EditMsg",
                                                        "CallP2P",
                                                        "SendText",
                                                        "SendSms",
                                                        "SendFileP2P",
                                                        "SendContacts",
                                                        "SendVideoMsg",
                                                        "SendMediaMsg",
                                                        "ChangeModerated"],
                                       "createdat": Data.msgTimeStr,
                                       "creator": "8:{0}".format(Data.nonContactId),
                                       "creatorcid": "0",
                                       "historydisclosed": "true",
                                       "joiningenabled": "true",
                                       "picture": "URL@https://api.asm.skype.com/v1/objects/"
                                                  "{0}/views/avatar_fullsize".format(Data.asmId),
                                       "topic": "Team chat"},
                        "type": "Thread",
                        "version": Data.msgTime})
    # Retrieve messages for a single conversation.
    responses.add(responses.GET, "{0}/users/ME/conversations/{1}/messages".format(*chatFmt),
                  status=200, content_type="application/json",
                  json={"messages": [{"clientmessageid": "1451606399999",
                                      "composetime": Data.msgTimeFmt,
                                      "content": "A message for the team.",
                                      "conversationLink": "{0}/users/ME/conversations/{1}".format(*chatFmt),
                                      "from": "{0}/users/ME/contacts/8:{1}".format(*nonConFmt),
                                      "id": Data.msgTimeStr,
                                      "messagetype": "Text",
                                      "originalarrivaltime": Data.msgTimeFmt,
                                      "type": "Message",
                                      "version": Data.msgTimeStr}]})
    # Send a new message to the conversation.
    responses.add(responses.POST, "{0}/users/ME/conversations/{1}/messages".format(*chatFmt),
                  status=200, content_type="application/json",
                  json={"OriginalArrivalTime": Data.msgTime})


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


class SkypeClientTest(unittest.TestCase):
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
        # Do the authentication.
        sk = Skype("fred.2", "password")
        # Tokens should be set.
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        # Messenger host should be the default.
        self.assertEqual(sk.conn.msgsHost, SkypeConnection.API_MSGSHOST)
        # Main endpoint should exist.
        self.assertEqual(sk.conn.endpoints["main"].id, "{{{0}}}".format(Data.endpointId))
        # Connected as our user, not a guest.
        self.assertTrue(sk.conn.connected)
        self.assertFalse(sk.conn.guest)
        self.assertEqual(sk.userId, Data.userId)

    @responses.activate
    def testAuthRedirect(self):
        """
        Complete the auth flow with a dummy username and password, including a messenger hostname redirect.
        """
        registerMocks(regTokenRedirect=True)
        # Do the authentication.
        sk = Skype("fred.2", "password")
        # Tokens should be set.
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        # Messenger host should be the alternative domain.
        self.assertEqual(sk.conn.msgsHost, Data.msgsHost)
        # Main endpoint should exist.
        self.assertEqual(sk.conn.endpoints["main"].id, "{{{0}}}".format(Data.endpointId))
        # Connected as our user, not a guest.
        self.assertTrue(sk.conn.connected)
        self.assertFalse(sk.conn.guest)
        self.assertEqual(sk.userId, Data.userId)

    @responses.activate
    def testGuestAuth(self):
        """
        Complete the auth flow as a guest joining a conversation.
        """
        registerMocks(guest=True)
        # Don't connect to start with.
        sk = Skype()
        self.assertFalse(sk.conn.connected)
        # Do the authentication.
        sk.conn.guestLogin(Data.chatShortId, "Name")
        # Tokens should be set.
        self.assertEqual(sk.conn.tokens["skype"], Data.skypeToken)
        self.assertEqual(sk.conn.tokens["reg"], "registrationToken={0}".format(Data.regToken))
        # Messenger host should be the default.
        self.assertEqual(sk.conn.msgsHost, SkypeConnection.API_MSGSHOST)
        # Main endpoint should exist.
        self.assertEqual(sk.conn.endpoints["main"].id, "{{{0}}}".format(Data.endpointId))
        # Connected as a guest user.
        self.assertTrue(sk.conn.connected)
        self.assertTrue(sk.conn.guest)
        self.assertEqual(sk.userId, Data.guestId)

    @responses.activate
    def testContactList(self):
        """
        Collect a list of contacts for the current user.
        """
        sk = mockSkype()
        # Expecting one contact.
        self.assertEqual(len(sk.contacts), 1)
        # Contact profile fields should be set.
        con = sk.contacts[Data.contactId]
        self.assertTrue(isinstance(con, SkypeContact))
        self.assertEqual(con.id, Data.contactId)
        self.assertEqual(str(con.name), "Joe Bloggs")
        self.assertEqual(len(con.phones), 3)
        self.assertEqual(con.authorised, True)
        self.assertEqual(con.blocked, False)
        # Check we can retrieve a user outside of the contact list.
        nonCon = sk.contacts[Data.nonContactId]
        self.assertTrue(isinstance(con, SkypeContact))
        self.assertEqual(nonCon.id, Data.nonContactId)
        self.assertEqual(nonCon.authorised, False)

    @responses.activate
    def testChatList(self):
        """
        Collect a list of conversations for the current user.
        """
        sk = mockSkype()
        # Expecting two conversations.
        recent = sk.chats.recent()
        self.assertEqual(len(recent), 2)
        # Check the 1-to-1 chat is present.
        chat = recent["8:{0}".format(Data.contactId)]
        self.assertEqual(chat.userId, Data.contactId)
        self.assertEqual(chat.userIds, [Data.contactId])
        # Check the group chat is present.
        groupChat = recent[Data.chatThreadId]
        self.assertEqual(groupChat.creatorId, Data.nonContactId)
        self.assertEqual(groupChat.adminIds, [Data.nonContactId])
        self.assertTrue(Data.userId in groupChat.userIds)
        self.assertTrue(Data.contactId in groupChat.userIds)
        self.assertTrue(Data.nonContactId in groupChat.userIds)
        self.assertEqual(groupChat.topic, "Team chat")
        self.assertTrue(groupChat.open)
        self.assertTrue(groupChat.history)

    @responses.activate
    def testChatGetMsgs(self):
        """
        Collect a list of messages for a conversation.
        """
        sk = mockSkype()
        chat = sk.chats[Data.chatThreadId]
        # Expecting one message.
        msgs = chat.getMsgs()
        self.assertEqual(len(msgs), 1)
        # Message properties should be present.
        msg = msgs[0]
        self.assertTrue(isinstance(msg, SkypeTextMsg))
        self.assertEqual(msg.id, Data.msgTimeStr)
        self.assertEqual(msg.time, datetime(2016, 1, 1))
        self.assertEqual(msg.userId, Data.nonContactId)
        self.assertEqual(msg.type, "Text")
        self.assertEqual(msg.content, "A message for the team.")

    @responses.activate
    def testChatSendMsgs(self):
        """
        Send various types of messages, and check the resulting :class:`SkypeMsg` instances.
        """
        sk = mockSkype()
        chat = sk.chats[Data.chatThreadId]
        # Send a plain text message.
        msg = chat.sendMsg("Word")
        self.assertTrue(isinstance(msg, SkypeTextMsg))
        self.assertEqual(msg.userId, Data.userId)
        self.assertEqual(msg.type, "Text")
        self.assertEqual(msg.content, "Word")
        # Send a rich text message.
        msg = chat.sendMsg(SkypeMsg.bold("Bold"), rich=True)
        self.assertTrue(isinstance(msg, SkypeTextMsg))
        self.assertEqual(msg.type, "RichText")

    def testUtils(self):
        """
        Various tests for parsing provided by :class:`.SkypeUtils`.
        """
        # Remove thread prefixes from thread identifiers.
        self.assertEqual(SkypeUtils.noPrefix("8:{0}".format(Data.userId)), Data.userId)
        self.assertEqual(SkypeUtils.noPrefix(Data.chatThreadId), Data.chatThreadId[3:])
        self.assertEqual(SkypeUtils.noPrefix(Data.liveContactId), Data.liveContactId)
        self.assertEqual(SkypeUtils.noPrefix("28:concierge"), "concierge")
        self.assertEqual(SkypeUtils.noPrefix("28:{0}".format(Data.botContactId)), Data.botContactId)
        # Extract user identifiers from URLs.
        self.assertEqual(SkypeUtils.userToId(""), None)
        self.assertEqual(SkypeUtils.userToId("{0}/users/8:{1}".format(Data.msgsHost, Data.contactId)), Data.contactId)
        self.assertEqual(SkypeUtils.userToId("{0}/users/8:{1}".format(Data.msgsHost, Data.liveContactId)),
                         Data.liveContactId)
        self.assertEqual(SkypeUtils.userToId("{0}/users/ME/contacts/8:{1}".format(Data.msgsHost, Data.contactId)),
                         Data.contactId)
        self.assertEqual(SkypeUtils.userToId("{0}/users/ME/contacts/8:{1}".format(Data.msgsHost, Data.liveContactId)),
                         Data.liveContactId)
        # Extract chat identifiers from URLs.
        self.assertEqual(SkypeUtils.chatToId(""), None)
        self.assertEqual(SkypeUtils.chatToId("{0}/conversations/8:{1}".format(Data.msgsHost, Data.liveContactId)),
                         "8:{0}".format(Data.liveContactId))
        self.assertEqual(SkypeUtils.chatToId("{0}/conversations/{1}".format(Data.msgsHost, Data.chatThreadId)),
                         Data.chatThreadId)
        self.assertEqual(SkypeUtils.chatToId("{0}/conversations/{1}".format(Data.msgsHost, Data.chatP2PThreadId)),
                         Data.chatP2PThreadId)


if __name__ == "__main__":
    unittest.main()
