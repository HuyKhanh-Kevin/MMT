class MessageType:
    LOGIN_REQUEST = 1
    LOGIN_RESPONSE = 2
    CHAT_MESSAGE = 3
    ACK = 4
    HEARTBEAT = 5
    USER_LIST_REQUEST = 6
    USER_LIST_RESPONSE = 7
    FILE_REQUEST = 8
    FILE_CHUNK = 9
    ERROR = 10
    FILE_DONE = 11
    SIGNUP_REQUEST = 12
    SIGNUP_RESPONSE = 13
    FILE_ACCEPTED = 14
    FILE_REJECTED = 15
    REQ_RESEND = 16
    ERROR_FILE = 17
    PRESENCE_UPDATE = 18
    LOGOUT_REQUEST = 19
    LOGOUT_RESPONSE = 20

    @staticmethod
    def isValidMessage(type):
        if 1 <= type <= 20:
            return True
        else:
            return False