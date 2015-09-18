# SkyPy

A highly unofficial Python library for interacting with the Skype HTTP API.  Adapted from [ShyykoSerhiy's skyweb API for node.js](https://github.com/ShyykoSerhiy/skyweb).

## Here be dragons

This code is currently very rough around the edges, and is liable to fall apart if the upstream API changes.

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