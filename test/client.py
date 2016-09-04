#!/usr/bin/env python

from datetime import datetime, timedelta
import time
import re
import unittest

import responses

from skpy import Skype, SkypeConnection, SkypeContact, SkypeMsg


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
    contactId = "joe.4"
    nonContactId = "anna.7"
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
    # Retrieve a list of contacts.
    responses.add(responses.GET, "{0}/users/{1}/contacts".format(SkypeConnection.API_CONTACTS, Data.userId),
                  status=200, content_type="application/json",
                  json={"contacts": [{"authorized": True,
                                      "avatar_url": "https://api.skype.com/users/{0}/profile/avatar"
                                                    .format(Data.contactId),
                                      "blocked": False,
                                      "display_name": "Joe Bloggs",
                                      "id": Data.contactId,
                                      "locations": [{"city": "London", "state": None, "country": "GB"}],
                                      "mood": "Happy <ss type=\"laugh\">:D</ss>",
                                      "name": {"first": "Joe", "surname": "Bloggs", "nickname": "Joe Bloggs"},
                                      "phones": [{"number": "+442099887766", "type": 0},
                                                 {"number": "+442020900900", "type": 1},
                                                 {"number": "+447711223344", "type": 2}],
                                      "type": "skype"},
                                     {"authorized": False,
                                      "blocked": False,
                                      "display_name": "Anna Cooper",
                                      "id": Data.nonContactId,
                                      "name": {"first": "Anna", "surname": "Cooper"},
                                      "suggested": True,
                                      "type": "skype"}]})
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

    @responses.activate
    def testContactList(self):
        """
        Collect a list of contacts for the current user.
        """
        sk = mockSkype()
        self.assertEqual(len(sk.contacts), 1)
        con = sk.contacts[Data.contactId]
        self.assertTrue(isinstance(con, SkypeContact))
        self.assertEqual(con.id, Data.contactId)
        self.assertEqual(str(con.name), "Joe Bloggs")
        self.assertEqual(len(con.phones), 3)
        self.assertEqual(con.authorised, True)
        self.assertEqual(con.blocked, False)
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
        recent = sk.chats.recent()
        self.assertEqual(len(recent), 2)
        chat = recent["8:{0}".format(Data.contactId)]
        self.assertEqual(chat.userId, Data.contactId)
        self.assertEqual(chat.userIds, [Data.contactId])
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
    def testChatMsgs(self):
        """
        Collect a list of messages for a conversation, and send a message.
        """
        sk = mockSkype()
        chat = sk.chats[Data.chatThreadId]
        msgs = chat.getMsgs()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertTrue(isinstance(msg, SkypeMsg))
        self.assertEqual(msg.id, Data.msgTimeStr)
        self.assertEqual(msg.time, datetime(2016, 1, 1))
        self.assertEqual(msg.userId, Data.nonContactId)
        self.assertEqual(msg.type, "Text")
        self.assertEqual(msg.content, "A message for the team.")
        msg = chat.sendMsg("Word.", rich=True)
        self.assertTrue(isinstance(msg, SkypeMsg))
        self.assertEqual(msg.userId, Data.userId)
        self.assertEqual(msg.type, "RichText")
        self.assertEqual(msg.content, "Word.")


if __name__ == "__main__":
    unittest.main()
