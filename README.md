# SkyPy

An unofficial Python library for interacting with the Skype HTTP API.

## Here be dragons

This code is liable to fall apart if any part of the upstream API changes.  You have been warned.

## Requirements

* [BeautifulSoup](http://www.crummy.com/software/BeautifulSoup/)
* [Requests](http://www.python-requests.org/en/latest/)

## Getting started

```python
from SkyPy import Skype
sk = Skype(username, password, tokenFile) # connect to Skype

sk.user # you
sk.contacts # your contacts
sk.getChats() # recent conversations
sk.getRequests() # contact requests
sk.getEvents() # presences, new messages etc.

buddychat = sk.contacts[buddyname].chat # 1-to-1 conversation
groupchat = sk.createChat() # new group conversation
```

A full class reference can be found [in the wiki](https://github.com/OllieTerrance/SkyPy/wiki/Classes).

## State-synced methods

Some APIs, such as recent conversations or messages, include a state URL for the next query -- this allows you to fetch the next chunk of data without resending any duplicates.  Wrapper methods for APIs that support state syncing (e.g. `Skype.getChats()`) automatically handle this for you.

## Rate limiting and session reuse

If you make too many authentication attempts, the Skype API may temporarily rate limit you, or require a captcha to continue.  For the latter, you will need to complete this in a browser with a matching IP address.

To avoid this, you should reuse the Skype token where possible.  A token only appears to last 24 hours (web.skype.com forces re-authentication after that time), though you can check the expiry with `sk.tokenExpiry`.  Pass a filename as the third argument to the `Skype()` constructor to read and write session information to that file.

## Writing a bot

Create a class that subclasses `SkypeBot`, then override the `onEvent(event)` method to handle incoming messages.

```python
import re
from SkyPy import SkypeBot, SkypeMessageEvent
class MyBot(SkypeBot):
    def __init__(self):
        super(SkypeBot, self).__init__(username, password)
    def onEvent(self, event):
        if isinstance(event, SkypeMessageEvent)
          and not event.userId == self.userId:
            if re.search("ping", event.content, re.IGNORECASE):
                event.chat.sendMsg("Pong!")
```

The bot will immediately start processing events, though you can set `loop=False` in the super `__init__` to disable this (in which case call `loop()` when ready).
