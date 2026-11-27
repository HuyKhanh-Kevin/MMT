#
# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# StreapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#


"""
app.sampleapp
~~~~~~~~~~~~~~~~~

"""

import json

from  daemon import StreapRous

app = StreapRous()


_account_routes = None


def configure_account_sessions(sessions):
    from apps.routes.account_http_routes import AccountHttpRoutes
    global _account_routes
    if sessions is None:
        _account_routes = None
    else:
        _account_routes = AccountHttpRoutes(sessions)


def _account_response(method, path, headers, body):
    if _account_routes is None:
        result = {"status": "failed", "reason": "ACCOUNT_API_NOT_CONFIGURED"}
    else:
        _, result = _account_routes.dispatch(method, path, headers, body)


    return json.dumps(result).encode("utf-8")


@app.route('/login', methods=['POST'])
def login(headers=None, body=b""):
    return _account_response("POST", "/login", headers or {}, body)


@app.route('/signup', methods=['POST'])
def signup(headers=None, body=b""):
    return _account_response("POST", "/signup", headers or {}, body)


@app.route('/logout', methods=['POST'])
def logout(headers=None, body=b""):
    return _account_response("POST", "/logout", headers or {}, body)


@app.route('/users', methods=['GET'])
def users(headers=None, body=b""):
    return _account_response("GET", "/users", headers or {}, body)


@app.route('/session', methods=['GET'])
def session(headers=None, body=b""):
    return _account_response("GET", "/session", headers or {}, body)


@app.route('/heartbeat', methods=['POST'])
def heartbeat(headers=None, body=b""):
    return _account_response("POST", "/heartbeat", headers or {}, body)


@app.route("/echo", methods=["POST"])
def echo(headers="guest", body="anonymous"):
    print("[SampleApp] received body {}".format(body))

    try:
        message = json.loads(json.dumps(body))
        data = {"received": message }
        # Convert to JSON string
        json_str = json.dumps(data)
        return (json_str.encode("utf-8"))
    except json.JSONDecodeError:
        data = {"error": "Invalid JSON"}
        # Convert to JSON string
        json_str = json.dumps(data)
        return (json_str.encode("utf-8"))


@app.route('/hello', methods=['PUT'])
async def hello(headers, body):
    """
    Handle greeting via PUT request.

    This route prints a greeting message to the console using the provided headers
    and body.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or message payload.
    """
    print("[SampleApp] ['PUT'] **ASYNC** Hello in {} to {}".format(headers, body))
    data =  {"id": 1, "name": "Alice", "email": "alice@example.com"}

    # Convert to JSON string
    json_str = json.dumps(data)
    return (json_str.encode("utf-8"))

@app.route('/upload', methods=['POST'])
def upload_file(headers, body):
    try:
        # Get file and prepare folder
        filename = headers.get(
            'x-filename', 'upload.bin'
        )

        filename = os.path.basename(
            filename.replace('\\', '/')
        )

        if not filename:
            return json.dumps({
                "error": "Invalid filename"
            }).encode("utf-8")

        upload_dir = os.path.join(
            os.path.dirname(__file__),
            "uploads"
        )
        os.makedirs(upload_dir, exist_ok=True)

        # Get file bytes
        if isinstance(body, str):
            file_content = body.encode("utf-8")
        elif isinstance(body, bytes):
            file_content = body
        else:
            raise TypeError("Invalid file body")

        # Save file
        filepath = os.path.join(upload_dir, filename)

        with open(filepath, "wb") as f:
            f.write(file_content)

        # Return JSON response
        result = {
            "message": "Upload successful",
            "filename": filename,
            "size": len(file_content)
        }

        return json.dumps(result).encode("utf-8")

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }).encode("utf-8")

def create_sampleapp(ip, port):
    # Prepare and launch the RESTful application
    app.prepare_address(ip, port)
    app.run()

