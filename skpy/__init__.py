"""
Root of the SkPy module.  Classes from all submodules are imported here for convenience.
"""

from skpy.core import Skype, SkypeEventLoop
from skpy.conn import SkypeConnection, SkypeEndpoint, SkypeAuthException
from skpy.user import SkypeUser, SkypeContact, SkypeContacts, SkypeRequest
from skpy.chat import SkypeChat, SkypeSingleChat, SkypeGroupChat, SkypeChats
from skpy.msg import SkypeMsg, SkypeContactMsg, SkypeFileMsg, SkypeImageMsg, SkypeCallMsg, SkypeMemberMsg, \
                     SkypeAddMemberMsg, SkypeRemoveMemberMsg
from skpy.event import SkypeEvent, SkypePresenceEvent, SkypeEndpointEvent, SkypeTypingEvent, \
                       SkypeMessageEvent, SkypeNewMessageEvent, SkypeEditMessageEvent, SkypeCallEvent, \
                       SkypeChatUpdateEvent, SkypeChatMemberEvent
from skpy.util import SkypeException, SkypeApiException
