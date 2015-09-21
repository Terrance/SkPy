import time

from .core import Skype
from .conn import SkypeConnection
from .event import SkypeMessageEvent

class SkypeBot(Skype):
    def __init__(self, user, pwd, tokenFile, autoAck=True):
        super(SkypeBot, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck
    def iter(self):
        for event in self.getEvents():
            if not hasattr(event, "sender") or not (event.sender == self.user.id):
                self.onEvent(event)
                if self.autoAck:
                    event.ack()
    def loop(self):
        while True:
            self.iter()
    def onEvent(self, event):
        pass
