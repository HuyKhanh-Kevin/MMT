"""Account-only HTTP contract, reusable by a socket host or StreapRous hooks."""

from apps.account_sessions import WebAccountError
from client.AccountClient import AccountRequestError
from common.JsonPayloadCodec import JsonPayloadCodec
from common.payload.signup_request import SignupRequest


class AccountHttpRoutes:
    def __init__(self, sessions):
        self.sessions = sessions

    def dispatch(self, method, path, headers, body=b""):
        methods = {"/signup": "POST", "/login": "POST", "/logout": "POST",
                   "/heartbeat": "POST", "/session": "GET", "/users": "GET"}
        if path not in methods:
            return 404, {"status": "failed", "reason": "NOT_FOUND"}
        if method != methods[path]:
            return 405, {"status": "failed", "reason": "METHOD_NOT_ALLOWED"}
        try:
            if path in ("/signup", "/login"):
                if isinstance(body, str):
                    body = body.encode("utf-8")
                credentials = JsonPayloadCodec.decode(body, SignupRequest)
                result = getattr(self.sessions, path[1:])(credentials.username, credentials.password)
                return (200 if result["status"] == "success" else 409), result
            normalized = {key.lower(): value for key, value in headers.items()}
            authorization = normalized.get("authorization", "")
            if not authorization.startswith("Bearer "):
                raise WebAccountError(401, "LOGIN_REQUIRED")
            token = authorization[7:]
            if not token or len(token) > 128:
                raise WebAccountError(401, "LOGIN_REQUIRED")
            action = {"/session": "status", "/heartbeat": "status",
                      "/users": "users", "/logout": "logout"}[path]
            return 200, getattr(self.sessions, action)(token)
        except WebAccountError as exc:
            return exc.status, {"status": "failed", "reason": exc.reason}
        except AccountRequestError as exc:
            return (401 if exc.code == 1004 else 400), {"status": "failed", "reason": exc.reason}
        except (ValueError, TypeError, RecursionError):
            return 400, {"status": "failed", "reason": "INVALID_PAYLOAD"}
        except OSError:
            return 503, {"status": "failed", "reason": "TRACKER_UNAVAILABLE"}
