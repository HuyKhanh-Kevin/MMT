class ProtocolConstants:
    """
    This class contains constants used in the protocol.
    """

    # Protocol version
    PROTOCOL_VERSION = 1.0

    HEADER_SIZE = 24
    MAX_JSON_PAYLOAD_SIZE = 1100
    MAX_TEXT_SIZE = 1000

    MAX_CHUNK_DATA_SIZE = 1024
    CHUNK_METADATA_SIZE = 12

    MAX_PACKET_SIZE = 1200    
