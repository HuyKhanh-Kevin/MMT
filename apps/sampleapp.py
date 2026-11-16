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

import sys
import os
import importlib.util
import json

from  daemon import StreapRous

app = StreapRous()

@app.route('/login', methods=['POST'])
def login(headers="guest", body="anonymous"):
    """
    Handle user login via POST request.

    This route simulates a login process and prints the provided headers and body
    to the console.

    :param headers (str): The request headers or user identifier.
    :param body (str): The request body or login payload.
    """
    print("[SampleApp] Logging in {} to {}".format(headers, body))
    data = {"message": "Welcome to the RESTful TCP WebApp"}

    # Convert to JSON string
    json_str = json.dumps(data)
    return (json_str.encode("utf-8"))

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

