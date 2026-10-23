"""Protocol library for TCP/IP to encode/decode messages.
"""

# -----Imports------------------------------------------------------------------
from dataclasses import dataclass
from enum import IntEnum
import struct
import numpy as np

# -----Constants----------------------------------------------------------------
MSG_PREFIX = 0x4F4F594E  # NYOO


class MsgType(IntEnum):
    SESSION_CONFIG = 0x01  # Py  -> UE5  uint8 num_crops, uint8 max_num_clicks
    CROP_REQUEST   = 0x02  # UE5 -> Py   uint8 advance (1 next, 0 resend current)
    CROP_CLOUD     = 0x03  # Py  -> UE5  header + float32 coord[N*3] + uint8 labels[N] (+ uint8 gt[N])
    CLICKS         = 0x04  # UE5 -> Py   header + click[M]
    LABELS         = 0x05  # Py  -> UE5  header + uint8 labels[N]
    FINISH         = 0x06  # UE5 -> Py   empty
    FINISHED       = 0x07  # Py  -> UE5  uint8 ok


MSG_HEADER_FORMAT = "<IBI"  # prefix, msg_type, payload_size
SESSION_CONFIG_FORMAT = "<BB"  # num_crops, max_num_clicks
CROP_REQUEST_FORMAT = "<B"  # advance
CLOUD_HEADER_FORMAT = "<BIB"  # crop_id, num_points, has_gt
CLICKS_HEADER_FORMAT = "<BI"  # crop_id, num_clicks
CLICK_FORMAT = "<IB"  # point_index, class_id
LABELS_HEADER_FORMAT = "<BI"  # crop_id, num_points
FINISHED_FORMAT = "<B"  # ok

CLASS_ID = {"FOLIAGE": 0, "STEM": 1, "GROUND": 2, "UNLABELLED": 31}
MODEL_CLASSES = (0, 1, 2)  # Only classes a user may click and the model can output


# -----Helper functions---------------------------------------------------------
def frame(msg_type, payload=b""):
    """Puts payload into a full message frame.

    Args:
        msg_type: Type of the message being framed.
        payload: Encoded message body.

    Returns:
        Full message (header + payload) in bytes.
    """
    header = struct.pack(MSG_HEADER_FORMAT, MSG_PREFIX, msg_type, len(payload))
    return header + payload


def parse_header(header):
    """Parse an incoming message to extract message type and payload length

    Args:
        header: Header of a message

    Returns:
        Type of message and length of payload

    Raises:
        ValueError: if prefix mismatches or the message type is unknown
    """
    prefix, msg_type, payload_len = struct.unpack(MSG_HEADER_FORMAT, header)
    if prefix != MSG_PREFIX:
        raise ValueError(f"Bad prefix: {prefix:#x}")
    return MsgType(msg_type), payload_len


# -----Classes------------------------------------------------------------------
@dataclass
class Cloud:
    """One crop streamed to UE5.

    Attributes:
        crop_id: Index of the crop in the plot.
        coord: (num_points, 3) float32, crop-local metres, UE frame (Y flipped).
        labels: (num_points,) uint8 current prediction.
        gt: (num_points,) uint8 ground truth, or None if the plot has none.
    """

    crop_id: int
    coord: np.ndarray
    labels: np.ndarray
    gt: np.ndarray = None


@dataclass
class Clicks:
    """A batch of user clicks on one crop.

    Attributes:
        crop_id: Crop the clicked points belong to.
        point_indices: (num_clicks,) uint32 indices into the crop's points.
        class_ids: (num_clicks,) uint8 class assigned to each clicked point.
    """

    crop_id: int
    point_indices: np.ndarray
    class_ids: np.ndarray

    def is_valid(self, num_points):
        """Validates the clicks against the resident crop.

        Raises:
            ValueError: If the batch is empty, a point index is out of range,
                or a class is not one the model predicts.
        """
        if len(self.point_indices) == 0:
            raise ValueError("empty click batch")
        if self.point_indices.max() >= num_points:
            raise ValueError(
                f"point index {self.point_indices.max()} out of range ({num_points})"
            )
        if not np.isin(self.class_ids, MODEL_CLASSES).all():
            raise ValueError(f"invalid class_id in clicks: {np.unique(self.class_ids)}")


# -----Functions----------------------------------------------------------------
def encode_session_config(num_crops, max_num_clicks):
    payload = struct.pack(SESSION_CONFIG_FORMAT, num_crops, max_num_clicks)
    return frame(MsgType.SESSION_CONFIG, payload)


def decode_session_config(payload):
    return struct.unpack(SESSION_CONFIG_FORMAT, payload)


def encode_crop_request(advance):
    return frame(MsgType.CROP_REQUEST, struct.pack(CROP_REQUEST_FORMAT, advance))


def decode_crop_request(payload):
    advance = struct.unpack(CROP_REQUEST_FORMAT, payload)[0]
    if advance not in (0, 1):
        raise ValueError(f"invalid advance flag: {advance}")
    return bool(advance)


def encode_crop_cloud(cloud):
    coord = np.ascontiguousarray(cloud.coord, dtype="<f4")
    labels = np.ascontiguousarray(cloud.labels, dtype="u1")
    num_points = len(labels)
    if coord.shape != (num_points, 3):
        raise ValueError(f"coord shape {coord.shape} does not match {num_points} labels")
    has_gt = cloud.gt is not None
    header = struct.pack(CLOUD_HEADER_FORMAT, cloud.crop_id, num_points, has_gt)
    parts = [header, coord.tobytes(), labels.tobytes()]
    if has_gt:
        gt = np.ascontiguousarray(cloud.gt, dtype="u1")
        if gt.shape != (num_points,):
            raise ValueError(f"gt shape {gt.shape} does not match {num_points} labels")
        parts.append(gt.tobytes())
    return frame(MsgType.CROP_CLOUD, b"".join(parts))


def decode_crop_cloud(payload):
    header_size = struct.calcsize(CLOUD_HEADER_FORMAT)
    crop_id, num_points, has_gt = struct.unpack_from(CLOUD_HEADER_FORMAT, payload)
    bytes_per_point = 12 + 1 + (1 if has_gt else 0)
    expected = header_size + num_points * bytes_per_point
    if len(payload) != expected:
        raise ValueError(f"cloud payload {len(payload)} B, expected {expected}")
    offset = header_size
    coord = np.frombuffer(payload, "<f4", num_points * 3, offset).reshape(-1, 3)
    offset += num_points * 12
    labels = np.frombuffer(payload, "u1", num_points, offset)
    offset += num_points
    gt = np.frombuffer(payload, "u1", num_points, offset) if has_gt else None
    return Cloud(crop_id, coord, labels, gt)


def encode_clicks(batch):
    clicks = b"".join(
        struct.pack(CLICK_FORMAT, i, c) for i, c in zip(batch.point_indices, batch.class_ids)
    )
    header = struct.pack(CLICKS_HEADER_FORMAT, batch.crop_id, len(batch.point_indices))
    return frame(MsgType.CLICKS, header + clicks)


def decode_clicks(payload):
    header_size = struct.calcsize(CLICKS_HEADER_FORMAT)
    crop_id, num_clicks = struct.unpack_from(CLICKS_HEADER_FORMAT, payload)
    if len(payload) != header_size + num_clicks * struct.calcsize(CLICK_FORMAT):
        raise ValueError(f"clicks payload {len(payload)} B does not match {num_clicks} clicks")
    clicks = list(struct.iter_unpack(CLICK_FORMAT, payload[header_size:]))
    point_indices = np.array([c[0] for c in clicks], dtype="<u4")
    class_ids = np.array([c[1] for c in clicks], dtype="u1")
    return Clicks(crop_id, point_indices, class_ids)


def encode_labels(crop_id, labels):
    labels = np.ascontiguousarray(labels, dtype="u1")
    header = struct.pack(LABELS_HEADER_FORMAT, crop_id, len(labels))
    return frame(MsgType.LABELS, header + labels.tobytes())


def decode_labels(payload):
    header_size = struct.calcsize(LABELS_HEADER_FORMAT)
    crop_id, num_points = struct.unpack_from(LABELS_HEADER_FORMAT, payload)
    if len(payload) != header_size + num_points:
        raise ValueError(f"labels payload {len(payload)} B does not match {num_points} points")
    labels = np.frombuffer(payload, "u1", num_points, header_size)
    return crop_id, labels


def encode_finish():
    return frame(MsgType.FINISH)


def encode_finished(ok):
    return frame(MsgType.FINISHED, struct.pack(FINISHED_FORMAT, int(ok)))


def decode_finished(payload):
    return bool(struct.unpack(FINISHED_FORMAT, payload)[0])
