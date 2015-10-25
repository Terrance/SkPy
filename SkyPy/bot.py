import time

from .core import Skype

class SkypeBot(Skype):
    """
    A skeleton class for producting automated Skype bots.

    Implementors should override the onEvent(event) method to react to messages and status changes.

    If loop is set, the bot will immediately start processing events.
    """
    def __init__(self, user, pwd, tokenFile, loop=True, autoAck=True):
        super(SkypeBot, self).__init__(user, pwd, tokenFile)
        self.autoAck = autoAck
        if loop:
            self.loop()
    def loop(self):
        """
        Handle any incoming events.  If autoAck is set, any 'ackrequired' URLs are automatically called.
        """
        while True:
            for event in self.getEvents():
                self.onEvent(event)
                if self.autoAck:
                    event.ack()
    def onEvent(self, event):
        pass
