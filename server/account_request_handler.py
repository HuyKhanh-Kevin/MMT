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
        try:
            self._check_header(request)
            message_type = request.header.messageType

            if message_type == MessageType.SIGNUP_REQUEST:
                result = self.auth.signup(request, connection, source_ip)
            elif message_type == MessageType.LOGIN_REQUEST:
                result = self.auth.login(request, connection, source_ip)
            elif message_type == MessageType.LOGOUT_REQUEST:
                result = self.auth.logout(request, connection, source_ip)
            else:
                raise AccountException(1003, "UNSUPPORTED_MESSAGE")

            response_type, receiver, body = result
            return ControlPackets.create(
                str(response_type), request.header.sequenceNumber, 0, receiver, body
            )
        except AccountException as error:
            return self.error(request, error.code, error.reason)
        except (ValueError, TypeError, RecursionError):
            return self.error(request, 1003, "INVALID_PAYLOAD")

    def handle_udp(self, request, source):
        try:
            self._check_header(request)
            message_type = request.header.messageType

            if message_type == MessageType.HEARTBEAT:
                self.tracker.heartbeat(request, source)
                return None
            elif message_type == MessageType.USER_LIST_REQUEST:
                response_type, receiver, body = self.tracker.users(request, source)
                return ControlPackets.create(
                    str(response_type), request.header.sequenceNumber, 0, receiver, body
                )
            else:
                raise AccountException(1003, "UNSUPPORTED_MESSAGE")
        except AccountException as error:
            return self.error(request, error.code, error.reason)
        except (ValueError, TypeError, RecursionError):
            return self.error(request, 1003, "INVALID_PAYLOAD")

    def _check_header(self, request):
        PacketCodec.encode(request)
        header = request.header
        if header.flags != 0 or header.streamID != 0:
            raise AccountException(1003, "INVALID_CONTROL_HEADER")
        if header.sequenceNumber == 0 or header.receiverID != 0:
            raise AccountException(1003, "INVALID_CONTROL_HEADER")

    @staticmethod
    def error(request, code, reason):
        header = request.header
        body = ErrorPayload(code, reason, header.streamID, header.sequenceNumber)
        return ControlPackets.create(
            str(MessageType.ERROR), header.sequenceNumber, 0, header.senderID, body
        )
