"""Validate account envelopes and route requests without owning sockets/threads."""

from apps.routes.auth_routes import AuthRoutes
from apps.routes.tracker_routes import TrackerRoutes
from common.ControlPackets import ControlPackets
from common.MessageType import MessageType
from common.PacketCodec import PacketCodec
from common.payload.ErrorPayload import ErrorPayload
from server.account_exception import AccountException


class AccountRequestHandler:
    def __init__(self, accounts, sessions, directory):
        self.auth = AuthRoutes(accounts, sessions)
        self.tracker = TrackerRoutes(sessions, directory)

    def handle_tcp(self, connection, source_ip, request):
        return self._handle(request, self.auth.routes, connection, source_ip)

    def handle_udp(self, request, source):
        return self._handle(request, self.tracker.routes, source)

    def _handle(self, request, routes, *context):
        try:
            # Adapters calling the handler directly get the same checks as PacketIO.
            PacketCodec.encode(request)
            header = request.header
            if header.flags != 0 or header.streamID != 0 or header.sequenceNumber == 0 or header.receiverID != 0:
                raise AccountException(1003, "INVALID_CONTROL_HEADER")
            route = routes.get(header.messageType)
            if route is None:
                raise AccountException(1003, "UNSUPPORTED_MESSAGE")
            result = route(request, *context)
            if result is None:
                return None
            message_type, receiver, body = result
            return ControlPackets.create(str(message_type), header.sequenceNumber, 0, receiver, body)
        except AccountException as exc:
            return self.error(request, exc.code, exc.reason)
        except (ValueError, TypeError, RecursionError):
            return self.error(request, 1003, "INVALID_PAYLOAD")

    @staticmethod
    def error(request, code, reason):
        header = request.header
        return ControlPackets.create(str(MessageType.ERROR), header.sequenceNumber,
                                     0, header.senderID,
                                     ErrorPayload(code, reason, header.streamID, header.sequenceNumber))
