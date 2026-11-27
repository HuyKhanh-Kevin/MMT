from client.AccountClient import AccountRequestError
from client.Client import Client as AccountUIClient
from common.MessageType import MessageType
from common.payload.UserListRequest import UserListRequest


class Client(AccountUIClient):
    def __init__(self, server_ip, server_port, udp_port, peer_tcp_port, file_udp_port):
        self.user_list_users = []
        self.file_transfer = None
        super().__init__(server_ip, server_port, udp_port, peer_tcp_port, file_udp_port)

    def get_authenticated(self):
        return self.authenticated

    def get_running(self):
        return self.running

    def set_file_transfer(self, file_transfer):
        self.file_transfer = file_transfer

    def get_outgoing_stream(self, receiver):
        return self._outgoing_stream_id(receiver)

    def _display_users(self, users):
        self.user_list_users = list(users)
        super()._display_users(users)

    def _notify(self, method, *args):
        if method == "display_logout_response":
            if self.listener is not None:
                self.listener.display_logout_response("success")
        else:
            super()._notify(method, *args)

    def send_tcp_packet(self, packet):
        try:
            return super().send_tcp_packet(packet)
        except AccountRequestError as error:
            self._notify("display_error", error.code, error.reason)
        except OSError as error:
            self._notify("display_error", 1004, str(error))

    def send_udp_packet(self, packet):
        try:
            users = super().send_udp_packet(packet)
            if packet.header.messageType == MessageType.USER_LIST_REQUEST:
                self.user_list_users = list(users)
            return users
        except AccountRequestError as error:
            self._notify("display_error", error.code, error.reason)
        except OSError as error:
            self._notify("display_error", 1004, str(error))

    def create_user_list_packet(self, cursor=None):
        current = self._require_login()
        return self._account_packet(MessageType.USER_LIST_REQUEST,
                                    UserListRequest(current.token, cursor), current.user_id)

    def request_user_list(self):
        return self.send_udp_packet(self.create_user_list_packet())

    def create_private_message_packet(self, receiver, message):
        return self.create_private_chat_packet(receiver, message)

    def create_global_message_packet(self, message):
        return self.create_global_chat_packet(message)
