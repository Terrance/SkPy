# SkyPy

An unofficial Python library for interacting with the Skype HTTP API.

## Here be dragons

This code is liable to fall apart if any part of the upstream API changes.  You have been warned.

## Requirements

* Python 2.6+ (includes 3.x)
* [BeautifulSoup](http://www.crummy.com/software/BeautifulSoup/)
* [Requests](http://www.python-requests.org/en/latest/)

## Getting started

```python
from SkyPy import Skype
sk = Skype(username, password, tokenFile) # connect to Skype

sk.user # you
sk.contacts # your contacts
sk.chats # your conversations

buddychat = sk.contacts[buddyname].chat # 1-to-1 conversation
groupchat = sk.chats.create([buddyname]) # new group conversation

groupchat.sendMsg(content) # plain-text message
groupchat.sendFile(open(filename, "rb"), filename) # file upload
groupchat.sendContact(sk.contacts[buddyname]) # contact sharing
```

Check the documentation for [more examples](http://sandbox.t.allofti.me/skypy/usage.html) or [the full API](http://sandbox.t.allofti.me/skypy/api.html).

## State-synced methods

Some APIs, such as recent conversations or messages, include a state URL for the next query -- this allows you to fetch the next chunk of data without resending any duplicates.  Wrapper methods for APIs that support state syncing (e.g. `SkypeChat.getMsgs()`) automatically handle this for you.

## Rate limiting and session reuse

If you make too many authentication attempts, the Skype API may temporarily rate limit you, or require a captcha to continue.  For the latter, you will need to complete this in a browser with a matching IP address.

To avoid this, you should reuse the Skype token where possible.  A token only appears to last 24 hours (web.skype.com forces re-authentication after that time), though you can check the expiry with `sk.tokenExpiry`.  Pass a filename as the third argument to the `Skype()` constructor to read and write session information to that file.

## Writing event-processing programs

Make your class a subclass of `SkypeEventLoop`, then override the `onEvent(event)` method to handle incoming messages and other events.

```python
from SkyPy import SkypeEventLoop, SkypeNewMessageEvent
class SkypePing(SkypeEventLoop):
    def __init__(self):
        super(SkypePing, self).__init__(username, password)
    def onEvent(self, event):
        if isinstance(event, SkypeNewMessageEvent) \
          and not event.msg.userId == self.userId \
          and "ping" in event.msg.content:
            event.msg.chat.sendMsg("Pong!")
```

Create an instance and call its `loop()` method to start processing events.  For programs with a frontend (e.g. a custom client), you'll likely want to put the event loop in its own thread.
