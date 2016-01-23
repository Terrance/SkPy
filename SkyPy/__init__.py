"""
Root of the SkyPy module.  Classes from all submodules are imported here for convenience.
"""

from SkyPy.core import Skype, SkypeEventLoop
from SkyPy.conn import SkypeConnection, SkypeEndpoint, SkypeAuthException
from SkyPy.user import SkypeUser, SkypeContact, SkypeContacts, SkypeRequest
from SkyPy.chat import SkypeChat, SkypeSingleChat, SkypeGroupChat, SkypeChats
from SkyPy.msg import SkypeMsg, SkypeContactMsg, SkypeFileMsg, SkypeImageMsg, SkypeCallMsg, SkypeMemberMsg, \
                      SkypeAddMemberMsg, SkypeRemoveMemberMsg
from SkyPy.event import SkypeEvent, SkypePresenceEvent, SkypeEndpointEvent, SkypeTypingEvent, \
                        SkypeMessageEvent, SkypeNewMessageEvent, SkypeEditMessageEvent, SkypeCallEvent, \
                        SkypeChatUpdateEvent, SkypeChatMemberEvent
from SkyPy.util import SkypeException, SkypeApiException
