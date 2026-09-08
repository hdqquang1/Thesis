"""Test client using Open3D to visualize point cloud
"""


# -----Imports------------------------------------------------------------------
import argparse
import laspy
import logging
import numpy as np
import zlib
import socket
import sys
from server import Connection
import open3d as o3d

from protocol import (
    MsgType,
    CLASS_ID,
    Hello,
    Click,
    encode_hello,
    decode_ready,
    decode_full_labels,
    encode_click,
    decode_labels
)


# -----Constants----------------------------------------------------------------
COLOR_MAP = {
    0: (0, 255, 0),      # Green  - Foliage
    1: (255, 0, 0),      # Red    - Stem
    2: (0, 0, 255),      # Blue   - Ground
    3: (0, 255, 255),    # Cyan   - Undergrowth
    31: (160, 160, 160)  # Gray   - Unlabelled
}


# -----Logging-------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# -----Main---------------------------------------------------------------------
def main():
    # Load point cloud
    parser = argparse.ArgumentParser(
        description="Interactive segmentation Python module.")
    parser.add_argument("laz_path", help="Path to point cloud LAZ file.")
    args = parser.parse_args()

    logger.info("Loading point cloud from %s", args.laz_path)
    las = laspy.read(args.laz_path)
    points = np.vstack((las.x, las.y, las.z)).transpose().astype(np.float32)
    # labels = las.classification

    count = np.size(points, axis=0)
    checksum = zlib.crc32(np.ascontiguousarray(points).tobytes())
    logger.info("Loaded point cloud: %d points, checksum=%08x", count, checksum)

    # Connect to socket
    logger.info("Connecting to 127.0.0.1:9000")
    conn = Connection(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    conn.connect("127.0.0.1", 9000)
    logger.info("Connected")

    # Send handshake message
    msg = encode_hello(Hello(count, checksum))
    conn.send_message(msg)
    logger.info("Sent HELLO")

    # Receive ready message
    msg_type, payload = conn.recv_message()
    if msg_type != MsgType.READY:
        raise ValueError(f"invalid message type: {msg_type} != {MsgType.READY}")
    ready = decode_ready(payload)
    if ready.ok == 0:
        logger.warning("Python module not ready; aborting")
        sys.exit(1)
    logger.info("Python module ready")

    # Receive initial full inference
    msg_type, payload = conn.recv_message()
    if msg_type != MsgType.FULL_LABELS:
        raise ValueError(
            f"invalid message type: {msg_type} != {MsgType.FULL_LABELS}")
    full_labels = decode_full_labels(payload)
    logger.info("Received initial FULL_LABELS (%d labels)", len(full_labels))

    # Load point cloud for Open3D
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    # colors = np.array([COLOR_MAP[c] for c in full_labels]) / 255.0
    # Avoid loop through every points in the point cloud by indexing
    palette = np.zeros((256,3))
    for label, color in COLOR_MAP.items():
        palette[label] = color
    colors = palette[full_labels] / 255.0
    pcd.colors = o3d.utility.Vector3dVector(colors)
    logger.info("Point cloud ready for visualisation")

    try:
        while True:
            # Open3D visualisation
            logger.info("Opening Open3D picking window")
            vis = o3d.visualization.VisualizerWithEditing()
            vis.create_window()
            vis.add_geometry(pcd)
            vis.run()
            vis.destroy_window()
            picked = vis.get_picked_points()
            if not picked:
                logger.info("No points picked; exiting loop")
                break
            logger.info("Picked %d point(s)", len(picked))
            for p in picked:
                click_msg = encode_click(
                    Click(int(p), 0.0, 0.0, 0.0, CLASS_ID['UNLABELLED'], 1))
                conn.send_message(click_msg)
                logger.info("Sent CLICK: point_index=%d", int(p))
                msg_type, payload = conn.recv_message()
                if msg_type == MsgType.LABELS:
                    labels = decode_labels(payload)
                    logger.info(
                        "Received LABELS for %d point(s)",
                        len(labels.point_indices),
                    )
                    np.asarray(pcd.colors)[labels.point_indices] = np.array(
                        COLOR_MAP[labels.class_ids[0]]) / 255.0
    except ConnectionError:
        logger.info("Server disconnected")

    conn.close()
    logger.info("Connection closed")


if __name__ == "__main__":
    main()
