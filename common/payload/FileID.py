"""Shared UUIDv4 file-transfer ID helpers.

Use the same file_id string in FILE_REQUEST, FILE_ACCEPTED/REJECTED,
FILE_CHUNK, FILE_DONE, REQ_RESEND and ERROR_FILE.
"""

import uuid


def new_file_id() -> str:
    """Create a canonical lowercase UUIDv4 string for a transfer."""
    return str(uuid.uuid4())


def validate_file_id(file_id: str) -> str:
    """Validate a canonical lowercase UUIDv4 string; return unchanged."""
    if not isinstance(file_id, str):
        raise TypeError("file_id must be a UUID string")
    try:
        identifier = uuid.UUID(file_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("file_id must be a valid UUID") from exc
    if identifier.version != 4 or str(identifier) != file_id:
        raise ValueError("file_id must be a canonical lowercase UUIDv4 string")
    return file_id
