"""Integration of Python module.

Includes network and interactive segmentation modules.
"""


# -----Imports------------------------------------------------------------------
import argparse
import laspy
import logging
import numpy as np
import os
import sys
import open3d as o3d
import zlib

from server import Listener
from protocol import (
    MsgType,
    Ready,
    Labels,
    decode_hello,
    decode_click,
    encode_ready,
    encode_labels,
    encode_full_labels,
)


# -----Constants----------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 9000
BIN_DIR = "N:/Thesis/ISSR_VR/Saved"


# -----Logging-------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# -----Functions----------------------------------------------------------------
def load_canonical(bin_path):
    """Loads a canonical point cloud binary exported by UE5.

    The binary layout is: uint32 point count, uint32 UE hash/checksum,
    followed by count * 3 float32 point coordinates, then count uint8
    ground-truth labels.

    Args:
        bin_path: Path to the canonical .bin file.

    Returns:
        A tuple of (points, gt, count, ue_hash) where points is an
        (N, 3) float32 array scaled to metres with UE5's Y axis
        flipped, gt is a copy of the ground-truth labels, count is the
        point count, and ue_hash is the checksum read from the file.
    """
    with open(bin_path, 'rb') as f:
        count = int(np.frombuffer(f.read(4), np.uint32)[0])
        ue_hash = int(np.frombuffer(f.read(4), np.uint32)[0])
        pts = np.frombuffer(f.read(12 * count), np.float32).reshape(-1, 3)
        gt = np.frombuffer(f.read(count), np.uint8)
    hash = zlib.crc32(pts)
    assert len(pts) == count and len(gt) == count and ue_hash == hash
    points = pts * np.float32([0.01, -0.01, 0.01])
    return points, gt.copy(), count, ue_hash


# -----Main---------------------------------------------------------------------
def main():
    # Load point cloud
    parser = argparse.ArgumentParser(
        description="Interactive segmentation Python module.")
    parser.add_argument("laz_path", help="Path to point cloud LAZ file.")
    args = parser.parse_args()

    with laspy.open(args.laz_path) as f:
        las_min = np.array([f.header.x_min, f.header.y_min, f.header.z_min])

    bin_filename = args.laz_path.split("\\")[2].replace(".laz", ".bin")
    bin_path = os.path.join(BIN_DIR, bin_filename)
    logger.info("Loading point cloud")
    points, gt, expected_count, expected_checksum = load_canonical(bin_path)
    labels = gt.copy()  # Avoid changing ground truth
    # Testing with everything stem
    # labels = np.full(expected_count, 1, dtype=np.uint8)

    # Ensure 0 offset
    offset = las_min - points.min(axis=0)
    points += offset

    logger.info(
        "Loaded point cloud: %d points, checksum=%08x",
        expected_count, expected_checksum,
    )

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd_tree = o3d.geometry.KDTreeFlann(pcd)
    logger.info("Built KD-tree for point cloud")

    listener = Listener(HOST, PORT)
    logger.info("Listening on %s:%d", HOST, PORT)
    # Only one connection
    with listener.accept() as conn:
        logger.info("Client connected")

        # Handshake
        msg_type, payload = conn.recv_message()
        logger.info("Received HELLO")

        if msg_type != MsgType.HELLO:
            raise ValueError(
                f"invalid first message type: {msg_type} != {MsgType.HELLO}")

        hello = decode_hello(payload)
        logger.info(
            "HELLO payload: count=%d checksum=%08x",
            hello.count, hello.checksum,
        )

        if hello.count != expected_count or hello.checksum != expected_checksum:
            ready_msg = encode_ready(Ready(0))
            conn.send_message(ready_msg)
            logger.warning(
                "Handshake mismatch (expected count=%d checksum=%08x); "
                "sent READY(0), aborting",
                expected_count, expected_checksum,
            )
            sys.exit(1)

        ready_msg = encode_ready(Ready(1))
        conn.send_message(ready_msg)
        logger.info("Handshake OK; sent READY(1)")

        # Initial full inference
        # TODO: labels = seg_infer(points)

        full_labels_msg = encode_full_labels(labels)
        conn.send_message(full_labels_msg)
        logger.info("Sent initial FULL_LABELS (%d labels)", len(labels))

        # Server loop
        logger.info("Entering server loop")
        try:
            while True:
                msg_type, payload = conn.recv_message()

                if msg_type == MsgType.CLICK:
                    click = decode_click(payload)
                    logger.info(
                        "Received CLICK: point_index=%d class_id=%d",
                        click.point_index, click.class_id,
                    )

                    # TODO: point_indices = interseg_infer(click)
                    # conn.send_message(encode_labels(Labels(point_indices, class_ids)))
                    # class_ids depends on ISSR choose points based on selected class or fix all neighbour points regardless of class
                    [k, idx, _] = pcd_tree.search_knn_vector_3d(
                        pcd.points[click.point_index], 5000)
                    class_ids = np.full(k, click.class_id, dtype=np.uint8)
                    point_indices = list(idx)
                    conn.send_message(encode_labels(
                        Labels(point_indices, class_ids)))
                    logger.info("Sent LABELS for %d neighbour points", k)

                else:
                    raise ValueError(f"invalid message type: {msg_type}")
        except ConnectionError:
            logger.info("Client disconnected")

    listener.close()
    logger.info("Listener closed")


if __name__ == "__main__":
    main()
