class Packet:
    def __init__(self, header, payload: bytes):
        if header is None:
            raise ValueError("Header cannot be None")

        if not isinstance(payload, bytes):
            raise TypeError("Payload must be bytes")

        self.header = header
        self.payload = payload

    def getHeader(self):
        return self.header

    def getPayload(self) -> bytes:
        return self.payload