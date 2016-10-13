#!/usr/bin/env python

import os
import unittest
from getpass import getpass

from skpy import Skype, SkypeNewMessageEvent


# Slightly less verbose access to environment variables.
env = dict((x, os.getenv("SKPY_TESTSERVER_{0}".format(x.upper()))) for x in ("tokens", "recip"))


class SkypeServerTestBase(unittest.TestCase):
    """
    Base class for tests designed to interpret server responses.

    .. warning::
        This requires access to a live Skype account, the credentials for which will be read from **.tokens** (or from
        a file named in environment variable ``SKPY_TESTSERVER_TOKENS`` if set).  This can be accomplished in a shell::

            >>> from skpy import Skype
            >>> Skype(username, password, tokenFile=".tokens")

        You must also set ``SKPY_TESTSERVER_RECIP`` to a contact on the account that should receive test messages.
    """

    @classmethod
    def setUpClass(cls):
        cls.sk = Skype(tokenFile=env["tokens"] or ".tokens")
        if not cls.sk.conn.connected:
            raise RuntimeError("Token file is invalid")
        cls.recip = env["recip"]
        if not cls.recip:
            raise RuntimeError("No recipient specified (SKPY_TESTSERVER_RECIP)")


class SkypeServerReadTest(SkypeServerTestBase):
    """
    Basic, read-only tests on information provided by the server for the connected account.
    """

    def testSelf(self):
        """
        Retrieve the current user.
        """
        self.sk.contacts.cache.clear()
        self.assertTrue(self.sk.user.id == self.sk.userId, "Wrong user identifier")

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
        self.assertTrue(self.sk.contacts.bot("concierge").id == "concierge")
        self.assertTrue(self.sk.contacts.bots())

    def testChats(self):
        """
        Retrieve a conversation with the named recipient.
        """
        self.sk.chats.cache.clear()
        chatId = "8:{0}".format(self.recip)
        chat = self.sk.chats[chatId]
        self.assertTrue(chat.id == chatId, "Wrong chat: {0}".format(chat.id))
        self.assertTrue(chat.userId == self.recip, "Wrong recipient: {0}".format(chat.userId))

    def testTranslate(self):
        """
        Request a text translation.
        """
        self.assertTrue("en" in self.sk.translate.languages)
        self.sk.translate(self.sk.translate("Skype server test", "fr"), "en", "fr")

    def testServices(self):
        """
        Retrieve the services list for the current user.
        """
        self.assertTrue(self.sk.services)


class SkypeServerWriteTest(SkypeServerTestBase):
    """
    Specific test cases that require performing "write" actions on the connected account.
    """

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


class SkypeServerEventTest(SkypeServerTestBase):
    """
    Specific test cases that poll the event stream, and require external data (i.e. sending messages from another
    client to this user account).
    """

    @staticmethod
    def input(prompt):
        try:
            return raw_input(prompt)
        except NameError:
            return input(prompt)

    def testPasswordLogin(self):
        """
        Attempt a fresh login with a username and password.
        """
        user = self.sk.userId
        if user.startswith("live:"):
            user = self.input("> Microsoft account email address: ")
            pwd = getpass("> Microsoft account password: ")
        else:
            pwd = getpass("> Skype account password: ")
        sk = Skype(user, pwd)
        self.assertTrue(sk.conn.connected)

    def testMessageEvent(self):
        """
        Receive a message from the named recipient.
        """
        print("")
        print("> Send a message from {0} to {1} now.".format(self.sk.userId, self.recip))
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
