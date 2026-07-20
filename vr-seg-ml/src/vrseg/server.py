"""Blocking single-client TCP server.

Reads framed messages, dispatches on msg_type.
"""


# -----Imports------------------------------------------------------------------
import socket
import struct

from protocol import MSG_HEADER_FORMAT, parse_header


# -----Constants----------------------------------------------------------------
MSG_HEADER_SIZE = struct.calcsize(MSG_HEADER_FORMAT)
MAX_PAYLOAD = 1_000_000_000

# -----Classes------------------------------------------------------------------
class Connection:
    def __init__(self, sock: socket.socket):
        self.sock = sock

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.sock.close()

    def connect(self, host: str, port: int):
        self.sock.connect((host, port))

    def close(self):
        self.sock.close()

    def _recv_exactly(self, nbytes: int) -> bytes:
        """Read exactly n bytes"""
        msg = bytearray()
        while len(msg) < nbytes:
            chunk = self.sock.recv(nbytes - len(msg))
            if not chunk:
                raise ConnectionError("disconnected mid-message")
            msg.extend(chunk)  # extend() appends multiple bytes
        return bytes(msg)

    def recv_message(self) -> tuple[int, bytes]:
        """Read full frame message"""
        header = self._recv_exactly(MSG_HEADER_SIZE)
        msg_type, payload_len = parse_header(header)
        if payload_len > MAX_PAYLOAD:
            raise ValueError(f"payload_len too large: {payload_len}")
        payload = self._recv_exactly(payload_len)
        return msg_type, payload

    def send_message(self, msg: bytes):
        self.sock.sendall(msg)


class Listener:
    def __init__(self, host: str, port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1)

    def accept(self):
        s, _ = self.sock.accept()
        return Connection(s)

    def close(self):
        self.sock.close()
