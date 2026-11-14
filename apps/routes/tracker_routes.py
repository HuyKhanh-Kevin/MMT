"""UDP heartbeat/discovery routes. Presence is emitted by the transport host."""

from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.payload.heartbeat import Heartbeat
from common.payload.user_list_request import UserListRequest


class TrackerRoutes:
    def __init__(self, sessions, directory):
        self.sessions = sessions
        self.directory = directory
        self.routes = {
            MessageType.HEARTBEAT: self.heartbeat,
            MessageType.USER_LIST_REQUEST: self.users,
        }

    def heartbeat(self, request, source):
        payload = JsonPayloadCodec.decode(request.payload, Heartbeat)
        self.sessions.heartbeat(payload.session_id, request.header.senderID,
                                payload.heartbeat_seq, source)
        return None

    def users(self, request, source):
        payload = JsonPayloadCodec.decode(request.payload, UserListRequest)
        users = self.sessions.discover(payload.session_id, request.header.senderID, source)
        page = self.directory.page(payload.session_id, payload.cursor, users,
                                   request.header.sequenceNumber)
        return MessageType.USER_LIST_RESPONSE, request.header.senderID, page
