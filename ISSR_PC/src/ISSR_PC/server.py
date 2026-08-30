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
    """A single TCP connection used to send/receive framed protocol messages."""

    def __init__(self, sock):
        """Initializes the connection.

        Args:
            sock: An open or unconnected TCP socket to wrap.
        """
        self.sock = sock

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.sock.close()

    def connect(self, host, port):
        """Connects the underlying socket to a remote endpoint.

        Args:
            host: Remote host to connect to.
            port: Remote port to connect to.
        """
        self.sock.connect((host, port))

    def close(self):
        """Closes the underlying socket."""
        self.sock.close()

    def _recv_exactly(self, nbytes):
        """Reads exactly nbytes from the socket, blocking as needed.

        Args:
            nbytes: Number of bytes to read.

        Returns:
            The bytes read.

        Raises:
            ConnectionError: If the peer disconnects before nbytes
                bytes have been received.
        """
        msg = bytearray()
        while len(msg) < nbytes:
            chunk = self.sock.recv(nbytes - len(msg))
            if not chunk:
                raise ConnectionError("disconnected mid-message")
            msg.extend(chunk)  # extend() appends multiple bytes
        return bytes(msg)

    def recv_message(self):
        """Reads one full framed message from the socket.

        Returns:
            A tuple of (msg_type, payload) where msg_type is the raw
            message type from the header and payload is the message
            body bytes.

        Raises:
            ConnectionError: If the peer disconnects mid-message.
            ValueError: If the header prefix is invalid, or the
                declared payload_len exceeds MAX_PAYLOAD.
        """
        header = self._recv_exactly(MSG_HEADER_SIZE)
        msg_type, payload_len = parse_header(header)
        if payload_len > MAX_PAYLOAD:
            raise ValueError(f"payload_len too large: {payload_len}")
        payload = self._recv_exactly(payload_len)
        return msg_type, payload

    def send_message(self, msg):
        """Sends a full framed message.

        Args:
            msg: Framed message bytes to send.
        """
        self.sock.sendall(msg)


class Listener:
    """A TCP listening socket that accepts a single client connection."""

    def __init__(self, host, port):
        """Creates, binds, and starts listening on a TCP socket.

        Args:
            host: Local address to bind to.
            port: Local port to bind to.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1)

    def accept(self):
        """Blocks until a client connects.

        Returns:
            A Connection wrapping the accepted client socket.
        """
        s, _ = self.sock.accept()
        return Connection(s)

    def close(self):
        """Closes the listening socket."""
        self.sock.close()
