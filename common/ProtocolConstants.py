class ProtocolConstants:
    """Protocol-wide limits. Keep consistent across client and server."""

    PROTOCOL_VERSION = 2

    HEADER_SIZE = 24
    MAX_JSON_PAYLOAD_SIZE = 1100
    MAX_TEXT_SIZE = 1000

    MAX_CHUNK_DATA_SIZE = 1024
    CHUNK_METADATA_SIZE = 24  # UUID (16) + chunk order (4) + payload length (4)

    MAX_PACKET_SIZE = 1200
