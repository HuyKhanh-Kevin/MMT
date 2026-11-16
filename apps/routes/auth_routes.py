from common.JsonPayloadCodec import JsonPayloadCodec
from common.MessageType import MessageType
from common.payload.login_request import LoginRequest
from common.payload.login_response import LoginResponse
from common.payload.logout_request import LogoutRequest
from common.payload.logout_response import LogoutResponse
from common.payload.signup_request import SignupRequest
from common.payload.signup_response import SignupResponse
from server.account_exception import AccountException


class AuthRoutes:
    def __init__(self, accounts, sessions):
        self.accounts = accounts
        self.sessions = sessions

    def _logged_out(self, request, connection):
        if request.header.senderID != 0 or self.sessions.has_session(connection):
            raise AccountException(1003, "ALREADY_AUTHENTICATED")

    def signup(self, request, connection, source_ip):
        self._logged_out(request, connection)
        payload = JsonPayloadCodec.decode(request.payload, SignupRequest)
        try:
            self.accounts.signup(payload.username, payload.password)
            result = SignupResponse("success", None)
        except AccountException as exc:
            result = SignupResponse("failed", exc.reason)
        except OSError:
            result = SignupResponse("failed", "ACCOUNT_STORE_UNAVAILABLE")
        return MessageType.SIGNUP_RESPONSE, 0, result

    def login(self, request, connection, source_ip):
        self._logged_out(request, connection)
        payload = JsonPayloadCodec.decode(request.payload, LoginRequest)
        try:
            account = self.accounts.authenticate(payload.username, payload.password)
            created = self.sessions.login(account, source_ip, payload.tcp_port,
                                          payload.file_udp_port, connection)
            result = LoginResponse("success", created.session_id, account.user_id, None)
        except AccountException as exc:
            result = LoginResponse("failed", None, None, exc.reason)
        if result.user_id is None:
            receiver = 0
        else:
            receiver = result.user_id
        return MessageType.LOGIN_RESPONSE, receiver, result

    def logout(self, request, connection, source_ip):
        payload = JsonPayloadCodec.decode(request.payload, LogoutRequest)
        self.sessions.logout(payload.session_id, request.header.senderID, connection)
        return MessageType.LOGOUT_RESPONSE, request.header.senderID, LogoutResponse("success")
