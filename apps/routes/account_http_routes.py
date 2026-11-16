from apps.account_sessions import WebAccountError
from client.AccountClient import AccountRequestError
from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.signup_request import SignupRequest


class AccountHttpRoutes:
    def __init__(self, sessions):
        self.sessions = sessions

    def dispatch(self, method, path, headers, body=b""):
        if path in ("/signup", "/login", "/logout", "/heartbeat"):
            expected_method = "POST"
        elif path in ("/session", "/users"):
            expected_method = "GET"
        else:
            return 404, {"status": "failed", "reason": "NOT_FOUND"}

        if method != expected_method:
            return 405, {"status": "failed", "reason": "METHOD_NOT_ALLOWED"}

        try:
            if path == "/signup" or path == "/login":
                if isinstance(body, str):
                    body = body.encode("utf-8")
                credentials = JsonPayloadCodec.decode(body, SignupRequest)

                if path == "/signup":
                    result = self.sessions.signup(credentials.username, credentials.password)
                else:
                    result = self.sessions.login(credentials.username, credentials.password)

                if result["status"] == "success":
                    return 200, result
                else:
                    return 409, result


            authorization = ""
            for name, value in headers.items():
                if name.lower() == "authorization":
                    authorization = value

            if not authorization.startswith("Bearer "):
                raise WebAccountError(401, "LOGIN_REQUIRED")
            token = authorization[7:]
            if token == "" or len(token) > 128:
                raise WebAccountError(401, "LOGIN_REQUIRED")

            if path == "/users":
                result = self.sessions.users(token)
            elif path == "/logout":
                result = self.sessions.logout(token)
            else:

                result = self.sessions.status(token)
            return 200, result

        except WebAccountError as error:
            return error.status, {"status": "failed", "reason": error.reason}
        except AccountRequestError as error:
            if error.code == 1004:
                status = 401
            else:
                status = 400
            return status, {"status": "failed", "reason": error.reason}
        except (ValueError, TypeError, RecursionError):
            return 400, {"status": "failed", "reason": "INVALID_PAYLOAD"}
        except OSError:
            return 503, {"status": "failed", "reason": "TRACKER_UNAVAILABLE"}
