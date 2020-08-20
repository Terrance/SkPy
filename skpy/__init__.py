"""
Root of the SkPy module.  Classes from all submodules are imported here for convenience.
"""

from skpy.core import SkypeObj, SkypeObjs, SkypeEnum, SkypeException, SkypeApiException, SkypeAuthException
from skpy.util import SkypeUtils
from skpy.main import Skype, SkypeEventLoop, SkypeSettings, SkypeTranslator
from skpy.conn import SkypeConnection, SkypeAuthProvider, SkypeAPIAuthProvider, SkypeLiveAuthProvider, \
                      SkypeSOAPAuthProvider, SkypeRefreshAuthProvider, SkypeGuestAuthProvider, SkypeEndpoint
from skpy.user import SkypeUser, SkypeContact, SkypeBotUser, SkypeContacts, SkypeContactGroup, SkypeRequest
from skpy.chat import SkypeChat, SkypeSingleChat, SkypeGroupChat, SkypeChats
from skpy.msg import SkypeMsg, SkypeTextMsg, SkypeContactMsg, SkypeLocationMsg, SkypeCardMsg, \
                     SkypeFileMsg, SkypeImageMsg, SkypeCallMsg, SkypeMemberMsg, \
                     SkypeAddMemberMsg, SkypeChangeMemberMsg, SkypeRemoveMemberMsg
from skpy.event import SkypeEvent, SkypePresenceEvent, SkypeEndpointEvent, SkypeTypingEvent, \
                       SkypeMessageEvent, SkypeNewMessageEvent, SkypeEditMessageEvent, SkypeCallEvent, \
                       SkypeChatUpdateEvent, SkypeChatMemberEvent
