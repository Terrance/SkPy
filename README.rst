SkPy
====

An unofficial Python library for interacting with the Skype HTTP API.

Here be dragons
---------------

The upstream APIs used here are undocumented and are liable to change, which may cause parts of this library to fall apart in obvious or non-obvious ways.  You have been warned.

Requirements
------------

- Python 2.6+ (includes 3.x)
- `BeautifulSoup <http://www.crummy.com/software/BeautifulSoup/>`_
- `Requests <http://www.python-requests.org/en/latest/>`_

Getting started
---------------

The documentation gives some examples in more detail, as well as a full API specification, but here are the basics to get you started:

.. code:: python

    from skpy import Skype
    sk = Skype(username, password) # connect to Skype

    sk.user # you
    sk.contacts # your contacts
    sk.chats # your conversations

    ch = sk.chats.create(["joe.4", "daisy.5"]) # new group conversation
    ch = sk.contacts["joe.4"].chat # 1-to-1 conversation

    ch.sendMsg(content) # plain-text message
    ch.sendFile(open("song.mp3", "rb"), "song.mp3") # file upload
    ch.sendContact(sk.contacts["daisy.5"]) # contact sharing

    ch.getMsgs() # retrieve recent messages

Rate limits and sessions
------------------------

If you make too many authentication attempts, the Skype API may temporarily rate limit you, or require a captcha to continue. For the latter, you will need to complete this in a browser with a matching IP address.

To avoid this, you should reuse the Skype token where possible. A token only appears to last 24 hours (web.skype.com forces re-authentication after that time), though you can check the expiry with ``sk.tokenExpiry``. Pass a filename as the third argument to the ``Skype()`` constructor to read and write session information to that file.

Event processing
----------------

Make your class a subclass of ``SkypeEventLoop``, then override the ``onEvent(event)`` method to handle incoming messages and other events:

.. code:: python

    from skpy import SkypeEventLoop, SkypeNewMessageEvent
    class SkypePing(SkypeEventLoop):
        def __init__(self):
            super(SkypePing, self).__init__(username, password)
        def onEvent(self, event):
            if isinstance(event, SkypeNewMessageEvent) \
              and not event.msg.userId == self.userId \
              and "ping" in event.msg.content:
                event.msg.chat.sendMsg("Pong!")

Create an instance and call its ``loop()`` method to start processing events. For programs with a frontend (e.g. a custom client), you'll likely want to put the event loop in its own thread.
