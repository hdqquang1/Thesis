"""Wire protocol encode/decode.

Pure functions over bytes using the struct module — no sockets here.

Protocol message:
[uint32 prefix 0x39594040][uint8 msg_type][uint32 payload_len][payload]
[uint32 prefix 0x39594040] Magic number to indicate the start of message
[uint8 msg_type] Types of message. Like Client - Server model of ROS2
    - MSG_HELLO (0x01) (UE5 to Python): system initialisation
    - MSG_READY (0x02) (Python to UE5): ready for inference
    - MSG_CLICK (0x03) (UE5 to Python): a click in UE5
    - MSG_LABELS (0x04) (Python to UE5): list of propagated labelled points
    - MSG_FULL_LABELS (0x05) (Python to UE5): initial inference pass 
[uint32 payload_len] Size of the message content
[payload] Message content:
    - MSG_HELLO (0x01) (UE5 to Python): uint32 count, uint32 checksum
    - MSG_READY (0x02) (Python to UE5): 
    - MSG_CLICK (0x03) (UE5 to Python): uint32 point_index, float32 x, y, z, 
    uint8 class_id, uint8 positive_flag
    - MSG_LABELS (0x04) (Python to UE5): list of uint32 for point idices, list 
    of uint8 for class ids.
    - MSG_FULL_LABELS (0x05) (Python to UE5): numpy array of uint8 for class_ids
"""


# -----Imports------------------------------------------------------------------
from dataclasses import dataclass
from struct import pack, unpack, unpack_from, calcsize
import numpy as np


# -----Constants----------------------------------------------------------------
MSG_PREFIX = 0x39594040 # NYOO

MSG_HELLO = 0x01
MSG_READY = 0x02
MSG_CLICK = 0x03
MSG_LABELS = 0x04
MSG_FULL_LABELS = 0x05

MSG_HEADER_FORMAT = "<IBI"
MSG_HELLO_FORMAT = "<II"
MSG_READY_FORMAT = "<B"
MSG_CLICK_FORMAT = "<IfffBB"

CLASS_ID = {
    "FOLIAGE": 0,
    "STEM": 1,
    "GROUND": 2,
    "UNDERGROWTH": 3,
    "UNLABELLED": 255
}


# -----Helper functions---------------------------------------------------------
def frame(msg_type: int, payload: bytes) -> bytes:
    """Put payload into a full message frame"""
    header = pack(MSG_HEADER_FORMAT, MSG_PREFIX, msg_type, 
                    len(payload))
    return header + payload

def parse_header(header: bytes) -> tuple[int, int]:
    """Parse an incoming message to extract message type and payload length"""
    prefix, msg_type, payload_len = unpack(MSG_HEADER_FORMAT, 
                                            header)
    if prefix != MSG_PREFIX:
        raise ValueError(f"bad magic: {prefix:#x}")
    return (msg_type, payload_len)


# -----Classes------------------------------------------------------------------
@dataclass
class Hello:
    count: int
    checksum: int

    def is_valid(self):
        if self.count < 0:
            raise ValueError(f"invalid point count: {self.count}")
        
@dataclass
class Ready:
    ok: bool

    def is_valid(self):
        if self.ok not in (0,1):
            raise ValueError(f"invalid ok flag: {self.ok}")

@dataclass
class Click:
    point_index: int
    x: float
    y: float
    z: float
    class_id: int
    positive_flag: int

    def is_valid(self):
        if self.class_id not in CLASS_ID.values():
            raise ValueError(f"invalid class_id: {self.class_id}")
        if self.positive_flag not in (0, 1):
            raise ValueError(f"invalid positive_flag: {self.positive_flag}")

@dataclass
class Labels:
    point_indices: list
    class_ids: list

    def is_valid(self):
        if len(self.point_indices) != len(self.class_ids):
            raise ValueError(
                f"mismatch length: {len(self.point_indices)} != {len(self.class_ids)}")
        if any(cid not in CLASS_ID.values() for cid in self.class_ids):
            raise ValueError("invalid class_id in labels")


# -----Functions----------------------------------------------------------------
def encode_hello(hello: Hello) -> bytes:
    """Encode on UE5"""
    hello.is_valid()
    payload = pack(MSG_HELLO_FORMAT, hello.count, hello.checksum)
    return frame(MSG_HELLO, payload)

def decode_hello(payload: bytes) -> Hello:
    """Decode on Python module"""
    hello = Hello(*unpack(MSG_HELLO_FORMAT, payload))
    hello.is_valid()
    return hello

def encode_ready(ready: Ready) -> bytes:
    """Encode on Python module"""
    ready.is_valid()
    payload = pack(MSG_READY_FORMAT, ready.ok)
    return frame(MSG_READY, payload)

def decode_ready(payload: bytes) -> Ready:
    """Decode on UE5"""
    ready = Ready(unpack(MSG_READY_FORMAT, payload)[0])
    ready.is_valid()
    return ready

def encode_click(click: Click) -> bytes:
    """Encode on UE5"""
    click.is_valid()
    payload = pack(MSG_CLICK_FORMAT, click.point_index, click.x, click.y,
                click.z, click.class_id, click.positive_flag)
    return frame(MSG_CLICK, payload)

def decode_click(payload: bytes) -> Click:
    """Decode on Python module"""
    click = Click(*unpack(MSG_CLICK_FORMAT, payload))
    click.is_valid()
    return click

def encode_labels(labels: Labels) -> bytes:
    """Encode on Python module"""
    labels.is_valid()
    count = len(labels.point_indices)
    flat = [v for pair in zip(labels.point_indices, labels.class_ids) for v in pair]
    payload = pack("<I"+"IB"*count, count, *flat)
    return frame(MSG_LABELS, payload)

def decode_labels(payload: bytes) -> Labels:
    """Decode on UE5"""
    count = unpack_from("<I", payload)[0]
    rest = unpack_from("<" + "IB"*count, payload, offset=4)
    point_indices = list(rest[0::2])
    class_ids = list(rest[1::2])
    labels = Labels(point_indices, class_ids)
    labels.is_valid()
    return labels

def encode_full_labels(class_ids: np.ndarray) -> bytes:
    """Encode on Python module"""
    arr = np.asarray(class_ids, dtype=np.uint8)
    if not np.isin(arr, list(CLASS_ID.values())).all():
        raise ValueError("invalid class_id in full labels")
    payload = pack("<I", len(arr)) + arr.tobytes()
    return frame(MSG_FULL_LABELS, payload)

def decode_full_labels(payload: bytes) -> np.ndarray:
    """Decode on UE5"""
    count = unpack_from("<I", payload)[0]
    return np.frombuffer(payload, dtype=np.uint8, count=count, offset=4).copy()