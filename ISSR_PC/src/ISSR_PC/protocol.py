"""Protocol library for TCP/IP to encode/decode messages.
"""


# -----Imports------------------------------------------------------------------
from dataclasses import dataclass
from enum import IntEnum
import struct
import numpy as np


# -----Constants----------------------------------------------------------------
MSG_PREFIX = 0x39594040  # NYOO


class MsgType(IntEnum):
    HELLO = 0x01
    READY = 0x02
    CLICK = 0x03
    LABELS = 0x04
    FULL_LABELS = 0x05


MSG_HEADER_FORMAT = "<IBI"
MSG_HELLO_FORMAT  = "<II"
MSG_READY_FORMAT  = "<B"
MSG_CLICK_FORMAT  = "<IfffBB"


CLASS_ID = {
    "FOLIAGE":      0,
    "STEM":         1,
    "GROUND":       2,
    "UNDERGROWTH":  3,
    "UNLABELLED":   31
}


# -----Helper functions---------------------------------------------------------
def frame(msg_type: MsgType, payload: bytes) -> bytes:
    """Puts payload into a full message frame.

    Args:
        msg_type: Type of the message being framed.
        payload: Encoded message body.

    Returns:
        Full message (header + payload) in bytes.
    """
    header = struct.pack(MSG_HEADER_FORMAT, MSG_PREFIX, msg_type,
                         len(payload))
    return header + payload


def parse_header(header: bytes) -> tuple[MsgType, int]:
    """Parse an incoming message to extract message type and payload length

    Args:
        header: Header of a message

    Returns:
        Type of message and length of payload

    Raises:
        ValueError: if prefix mismatches
    """
    prefix, msg_type, payload_len = struct.unpack(MSG_HEADER_FORMAT,
                                                  header)
    if prefix != MSG_PREFIX:
        raise ValueError(f"Bad prefix: {prefix:#x}")
    return MsgType(msg_type), payload_len


# -----Classes------------------------------------------------------------------
@dataclass
class Hello:
    """Handshake payload sent by UE5 to identify the point cloud.

    Attributes:
        count: Number of points in the point cloud.
        checksum: Checksum of the point cloud, used to verify both sides
            loaded the same data.
    """
    count: int
    checksum: int

    def is_valid(self):
        """Validates field values.

        Raises:
            ValueError: If count is negative.
        """
        if self.count < 0:
            raise ValueError(f"invalid point count: {self.count}")


@dataclass
class Ready:
    """Handshake response sent by the Python module.

    Attributes:
        ok: 1 if the handshake succeeded, 0 otherwise. Kept as an int
            (rather than bool) to avoid other garbage values being
            treated as true.
    """
    ok: int  # int to avoid other garbage values treated as true

    def is_valid(self):
        """Validates field values.

        Raises:
            ValueError: If ok is not 0 or 1.
        """
        if self.ok not in (0, 1):
            raise ValueError(f"invalid ok flag: {self.ok}")


@dataclass
class Click:
    """A single point click/selection sent from UE5.

    Attributes:
        point_index: Index of the clicked point in the point cloud.
        x: X coordinate of the click (currently unused, reserved).
        y: Y coordinate of the click (currently unused, reserved).
        z: Z coordinate of the click (currently unused, reserved).
        class_id: Class to assign, one of CLASS_ID values.
        positive_flag: 1 for a positive click, 0 for a negative click.
    """
    point_index: int
    x: float
    y: float
    z: float
    class_id: int
    positive_flag: int

    def is_valid(self):
        """Validates field values.

        Raises:
            ValueError: If class_id is not a known class, or
                positive_flag is not 0 or 1.
        """
        if self.class_id not in CLASS_ID.values():
            raise ValueError(f"invalid class_id: {self.class_id}")
        if self.positive_flag not in (0, 1):
            raise ValueError(f"invalid positive_flag: {self.positive_flag}")


@dataclass
class Labels:
    """A sparse set of point index to class_id assignments.

    Attributes:
        point_indices: Indices of the labelled points.
        class_ids: Class assigned to each point, aligned by position
            with point_indices.
    """
    point_indices: list
    class_ids: list

    def is_valid(self):
        """Validates field values.

        Raises:
            ValueError: If point_indices and class_ids have different
                lengths, or if any class_id is not a known class.
        """
        if len(self.point_indices) != len(self.class_ids):
            raise ValueError(
                f"mismatch length: {len(self.point_indices)} != {len(self.class_ids)}")
        if any(cid not in CLASS_ID.values() for cid in self.class_ids):
            raise ValueError("invalid class_id in labels")


# -----Functions----------------------------------------------------------------
def encode_hello(hello: Hello) -> bytes:
    """Encodes a HELLO message. Called on UE5.

    Args:
        hello: Handshake payload to encode.

    Returns:
        Framed HELLO message in bytes.

    Raises:
        ValueError: If hello fails validation.
    """
    hello.is_valid()
    payload = struct.pack(MSG_HELLO_FORMAT, hello.count, hello.checksum)
    return frame(MsgType.HELLO, payload)


def decode_hello(payload: bytes) -> Hello:
    """Decodes a HELLO message payload. Called on the Python module.

    Args:
        payload: Raw HELLO payload bytes (without header).

    Returns:
        Decoded Hello.

    Raises:
        ValueError: If the decoded fields fail validation.
        struct.error: If payload does not match MSG_HELLO_FORMAT.
    """
    hello = Hello(*struct.unpack(MSG_HELLO_FORMAT, payload))
    hello.is_valid()
    return hello


def encode_ready(ready: Ready) -> bytes:
    """Encodes a READY message. Called on the Python module.

    Args:
        ready: Handshake response to encode.

    Returns:
        Framed READY message in bytes.

    Raises:
        ValueError: If ready fails validation.
    """
    ready.is_valid()
    payload = struct.pack(MSG_READY_FORMAT, ready.ok)
    return frame(MsgType.READY, payload)


def decode_ready(payload: bytes) -> Ready:
    """Decodes a READY message payload. Called on UE5.

    Args:
        payload: Raw READY payload bytes (without header).

    Returns:
        Decoded Ready.

    Raises:
        ValueError: If the decoded fields fail validation.
        struct.error: If payload does not match MSG_READY_FORMAT.
    """
    ready = Ready(struct.unpack(MSG_READY_FORMAT, payload)[0])
    ready.is_valid()
    return ready


def encode_click(click: Click) -> bytes:
    """Encodes a CLICK message. Called on UE5.

    Args:
        click: Click event to encode.

    Returns:
        Framed CLICK message in bytes.

    Raises:
        ValueError: If click fails validation.
    """
    click.is_valid()
    payload = struct.pack(MSG_CLICK_FORMAT, click.point_index, click.x, click.y,
                          click.z, click.class_id, click.positive_flag)
    return frame(MsgType.CLICK, payload)


def decode_click(payload: bytes) -> Click:
    """Decodes a CLICK message payload. Called on the Python module.

    Args:
        payload: Raw CLICK payload bytes (without header).

    Returns:
        Decoded Click.

    Raises:
        ValueError: If the decoded fields fail validation.
        struct.error: If payload does not match MSG_CLICK_FORMAT.
    """
    click = Click(*struct.unpack(MSG_CLICK_FORMAT, payload))
    click.is_valid()
    return click


def encode_labels(labels: Labels) -> bytes:
    """Encodes a LABELS message. Called on the Python module.

    Args:
        labels: Sparse point index/class_id assignments to encode.

    Returns:
        Framed LABELS message in bytes.

    Raises:
        ValueError: If labels fails validation.
    """
    labels.is_valid()
    count = len(labels.point_indices)
    flat = [v for pair in zip(labels.point_indices,
                              labels.class_ids) for v in pair]
    payload = struct.pack("<I"+"IB"*count, count, *flat)
    return frame(MsgType.LABELS, payload)


def decode_labels(payload: bytes) -> Labels:
    """Decodes a LABELS message payload. Called on UE5.

    Args:
        payload: Raw LABELS payload bytes (without header).

    Returns:
        Decoded Labels.

    Raises:
        ValueError: If the decoded fields fail validation.
        struct.error: If payload is malformed for the declared count.
    """
    count = struct.unpack_from("<I", payload)[0]
    rest = struct.unpack_from("<" + "IB"*count, payload, offset=4)
    point_indices = list(rest[0::2])
    class_ids = list(rest[1::2])
    labels = Labels(point_indices, class_ids)
    labels.is_valid()
    return labels


def encode_full_labels(class_ids: np.ndarray) -> bytes:
    """Encodes a FULL_LABELS message. Called on the Python module.

    Args:
        class_ids: Class id for every point in the point cloud, in
            point order.

    Returns:
        Framed FULL_LABELS message in bytes.

    Raises:
        ValueError: If any class_id is not a known class.
    """
    arr = np.asarray(class_ids, dtype=np.uint8)
    if not np.isin(arr, list(CLASS_ID.values())).all():
        raise ValueError("invalid class_id in full labels")
    payload = struct.pack("<I", len(arr)) + arr.tobytes()
    return frame(MsgType.FULL_LABELS, payload)


def decode_full_labels(payload: bytes) -> np.ndarray:
    """Decodes a FULL_LABELS message payload. Called on UE5.

    Args:
        payload: Raw FULL_LABELS payload bytes (without header).

    Returns:
        Array of class ids for every point, in point order.
    """
    count = struct.unpack_from("<I", payload)[0]
    return np.frombuffer(payload, dtype=np.uint8, count=count, offset=4).copy()
