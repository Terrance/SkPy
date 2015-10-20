import time

from .core import Skype

class SkypeBot(Skype):
    def __init__(self, user, pwd, tokenFile, autoAck=True):
        super(SkypeBot, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck
        self.setStatus("Online")
    def iter(self):
        for event in self.getEvents():
            self.onEvent(event)
            if self.autoAck:
                event.ack()
    def loop(self):
        while True:
            self.iter()
    def onEvent(self, event):
        pass
