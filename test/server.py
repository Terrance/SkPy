#!/usr/bin/env python

import os
import unittest

from skpy import Skype, SkypeNewMessageEvent


class SkypeServerTest(unittest.TestCase):
    """
    Tests for interpretation of server responses.

    .. warning:
        This requires access to a live Skype account, the credentials for which will be read from `.tokens` (or from
        a file named in environment variable `SKPY_TESTSERVER_TOKENS` if set).  This can be accomplished in a shell::

            >>> from skpy import Skype
            >>> Skype(username, password, tokenFile=".tokens")

        You must also set `SKPY_TESTSERVER_RECIP` to a contact on the account that should receive test messages.

    The more involved tests are separated out into :cls:`SkypeServerWritesTest` and :cls:`SkypeServerEventsTest`.
    """

    @classmethod
    def setUpClass(cls):
        cls.sk = Skype(tokenFile=os.getenv("SKPY_TESTSERVER_TOKENS", ".tokens"))
        if not cls.sk.conn.connected:
            raise RuntimeError("Token file is invalid")
        cls.recip = os.environ["SKPY_TESTSERVER_RECIP"]

    def testSettings(self):
        """
        Read all setting fields for the current user.
        """
        for setting in self.sk.settings.attrs:
            getattr(self.sk.settings, setting)

    def testContacts(self):
        """
        Retrieve the named recipient as a user and a contact.
        """
        self.sk.contacts.cache.clear()
        self.assertTrue(self.sk.contacts.user(self.recip).id == self.recip, "Failed to lookup user")
        self.assertTrue(self.recip in (contact.id for contact in self.sk.contacts), "No contacts returned")
        self.assertTrue(self.sk.contacts[self.recip].id == self.recip, "Failed to lookup cached contact")
        self.assertTrue(self.sk.contacts.contact(self.recip).id == self.recip, "Failed to lookup full contact")

    def testChats(self):
        """
        Retrieve a conversation with the named recipient.
        """
        self.sk.chats.cache.clear()
        chatId = "8:{0}".format(self.recip)
        chat = self.sk.chats[chatId]
        self.assertTrue(chat.id == chatId, "Wrong chat: {0}".format(chat.id))
        self.assertTrue(chat.userId == self.recip, "Wrong recipient: {0}".format(chat.userId))


class SkypeServerWritesTest(unittest.TestCase):
    """
    Specific test cases that require performing "write" actions on the connected account.
    """

    @classmethod
    def setUpClass(cls):
        cls.sk = Skype(tokenFile=os.getenv("SKPY_TESTSERVER_TOKENS", ".tokens"))
        cls.recip = os.environ["SKPY_TESTSERVER_RECIP"]

    def testGroupChats(self):
        """
        Create a group chat with the named recipient, send a test message, and invite a guest.
        """
        chat = self.sk.chats.create([self.recip])
        try:
            chat.setTopic("Skype server test")
            self.assertTrue(set(chat.userIds) == set([self.sk.userId, self.recip]),
                            "Wrong group recipients: {0}".format(", ".join(chat.userIds)))
            msg = chat.sendMsg("Test message.")
            self.assertTrue(msg.chatId == chat.id, "Wrong group chat: {0}".format(chat.id))
            self.assertTrue(msg.content == "Test message.", "Wrong message: {0}".format(msg.content))
            chat.setHistory(False)
            chat.setOpen(True)
            skGuest = Skype()
            skGuest.conn.guestLogin(chat.joinUrl, "Test")
            chatGuest = skGuest.chats[chat.id]
            try:
                msgGuest = chatGuest.sendMsg("Test message from guest.")
                self.assertTrue(msgGuest.chatId == chat.id, "Wrong guest group chat: {0}".format(chat.id))
                self.assertTrue(msgGuest.content == "Test message from guest.",
                                "Wrong guest message: {0}".format(msg.content))
            finally:
                chatGuest.leave()
                chat.setOpen(False)
        finally:
            chat.leave()
            chat.delete()


class SkypeServerEventsTest(unittest.TestCase):
    """
    Specific test cases that poll the event stream, and require external data (i.e. sending messages from another
    client to this user account).
    """

    @classmethod
    def setUpClass(cls):
        cls.sk = Skype(tokenFile=os.getenv("SKPY_TESTSERVER_TOKENS", ".tokens"))
        cls.recip = os.environ["SKPY_TESTSERVER_RECIP"]

    def testEvents(self):
        """
        Receive a message from the named recipient.
        """
        print("Send a message from {0} to {1} now.".format(self.sk.userId, self.recip))
        while True:
            dead = True
            for event in self.sk.getEvents():
                dead = False
                if isinstance(event, SkypeNewMessageEvent) and event.msg.chatId == "8:{0}".format(self.recip):
                    return
            if dead:
                self.fail("No events received")


if __name__ == "__main__":
    unittest.main()
