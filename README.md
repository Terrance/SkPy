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
sk.contacts # a list of your contacts
sk.getEvents() # a list of presences, new messages etc.
sk.sendMsg(conversationId, message) # say something
```

## Rate limiting and session reuse

If you make too many authentication attempts, the Skype API may temporarily rate limit you, or require a captcha to continue.  For the latter, you will need to complete this in a browser with a matching IP address.

To avoid this, you should reuse the Skype token where possible.  A token _usually_ lasts 24 hours (see `sk.tokenExpiry`).  Pass a filename as the third argument to the `Skype()` constructor to read and write session information to that file.
