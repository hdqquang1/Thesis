"""Test integration of Python module using KNN as interactive segmentation
method
"""


# -----Imports------------------------------------------------------------------
import argparse
import laspy
import logging
import numpy as np
import zlib
import sys
import open3d as o3d

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


# -----Logging-------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# -----Main---------------------------------------------------------------------
if __name__ == "__main__":
    # Load point cloud
    parser = argparse.ArgumentParser(
        description="Interactive segmentation Python module.")
    parser.add_argument("laz_path", help="Path to point cloud LAZ file.")
    args = parser.parse_args()

    logger.info("Loading point cloud from %s", args.laz_path)
    las = laspy.read(args.laz_path)
    points = np.vstack((las.x, las.y, las.z)).transpose().astype(np.float32)
    labels = las.classification

    expected_count = len(labels)  # Number of points = number of labels
    expected_checksum = zlib.crc32(np.ascontiguousarray(points).tobytes())
    logger.info(
        "Loaded point cloud: %d points, checksum=%08x",
        expected_count, expected_checksum,
    )

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

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        pcd_tree = o3d.geometry.KDTreeFlann(pcd)
        logger.info("Built KD-tree for point cloud")

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
                        pcd.points[click.point_index], 10000)
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
