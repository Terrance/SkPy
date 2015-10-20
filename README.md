# SkyPy

A highly unofficial Python library for interacting with the Skype HTTP API.  Adapted from [ShyykoSerhiy's skyweb API for node.js](https://github.com/ShyykoSerhiy/skyweb).

## Here be dragons

This code is liable to fall apart if any part of the upstream API changes.  You have been warned.

## Requirements

* [BeautifulSoup](http://www.crummy.com/software/BeautifulSoup/)
* [Requests](http://www.python-requests.org/en/latest/)

## Getting started

```python
from SkyPy import Skype
sk = Skype(username, password) # connect to Skype
sk.user # you
sk.contacts # your contacts
sk.getChats() # recent conversations
sk.getEvents() # presences, new messages etc.
```

## State-synced methods

Some APIs, such as conversations or messages within them, include a state URL for the next query -- this avoids resending any duplicate data.  Wrapper methods for APIs that support state syncing (e.g. `Skype.getChats()`) automatically handle this for you.

## Rate limiting and session reuse

If you make too many authentication attempts, the Skype API may temporarily rate limit you, or require a captcha to continue.  For the latter, you will need to complete this in a browser with a matching IP address.

To avoid this, you should reuse the Skype token where possible.  A token _usually_ lasts 24 hours (the actual expiry is stored in `sk.tokenExpiry`).  Pass a filename as the third argument to the `Skype()` constructor to read and write session information to that file.

## Writing a bot

Create a class that subclasses `SkypeBot`, then override the `onEvent(event)` method to handle incoming messages.

```python
import re
from SkyPy import SkypeBot, SkypeMessageEvent
class MyBot(SkypeBot):
    def __init__(self):
        super(SkypeBot, self).__init__(username, password, loop=True)
    def onEvent(self, event):
        if isinstance(event, SkypeMessageEvent)
          and not event.sender == self.user.id:
            if re.search("ping", event.body, re.IGNORECASE):
                self.sendMsg(event.chat, "Pong!")
```

To run a `SkypeBot`, call its `loop()` method.
