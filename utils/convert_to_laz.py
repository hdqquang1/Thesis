"""Converts a pickle labelled point cloud to LAZ
"""


# -----Imports------------------------------------------------------------------
import sys
import os
import pickle
import argparse
import numpy as np
import laspy


# -----Constant-----------------------------------------------------------------
COLOR_MAP = {
    0: (0, 255, 0),      # Green  - Foliage
    1: (255, 0, 0),      # Red    - Stem
    2: (0, 0, 255),      # Blue   - Ground
    3: (0, 255, 255),    # Cyan   - Undergrowth
}
DEFAULT_COLOR = (255, 255, 255)  # White for unmapped labels


# -----Functions----------------------------------------------------------------
def read_pickle(path):
    """Reads points and labels from an Nx4 pickle file.

    Args:
        path: Path to the pickle file (columns: x, y, z, label).

    Returns:
        A tuple of (points, labels): points is an (N, 3) float32
        array, labels is an (N,) uint8 array.
    """
    data = pickle.load(open(path, "rb"))
    points = data[:, :3].astype(np.float32)
    labels = data[:, 3].astype(np.uint8)
    return points, labels


def read_txt(path):
    """Reads points and labels from an Nx4 txt file.

    Args:
        path: Path to the txt file (columns: x, y, z, label).

    Returns:
        A tuple of (points, labels): points is an (N, 3) float32
        array, labels is an (N,) uint8 array.
    """
    data = np.loadtxt(path)
    points = data[:, :3].astype(np.float32)
    labels = data[:, 3].astype(np.uint8)

    # This source file's ground (2) and foliage (0) labels are swapped
    # relative to the rest of the files' convention.
    is_ground, is_foliage = labels == 2, labels == 0
    labels[is_ground] = 0
    labels[is_foliage] = 2

    return points, labels


def read_laz(input_path):
    """Reads points, classification, and RGB colour from a LAZ file.

    Args:
        input_path: Path to the input .laz file.

    Returns:
        A tuple of (points, classification, red, green, blue): points
        is an (N, 3) array, classification is an (N,) array, and
        red/green/blue are each an (N,) array of colour channel values.
    """
    las_in = laspy.read(input_path)
    points = np.vstack((las_in.x, las_in.y, las_in.z)).transpose()
    classification = np.asarray(las_in.classification)
    red = np.asarray(las_in.red)
    green = np.asarray(las_in.green)
    blue = np.asarray(las_in.blue)
    return points, classification, red, green, blue


def labels_to_colors(labels):
    """Maps classification labels to RGB colours via COLOR_MAP.

    Args:
        labels: (N,) array of classification labels.

    Returns:
        An (N, 3) uint16 array of RGB colours, scaled to the
        16-bit range LAS RGB fields use. Labels not present in
        COLOR_MAP are left black.
    """
    colors = np.zeros((len(labels), 3), dtype=np.uint16)
    for label, (r, g, b) in COLOR_MAP.items():
        colors[labels == label] = (r * 257, g * 257, b * 257)
    return colors


def write_laz(points, labels, output_path):
    """Writes points, classification labels, and RGB colour to a LAZ file.

    Args:
        points: (N, 3) array of x, y, z coordinates.
        labels: (N,) array of classification labels.
        output_path: Path to write the .laz file to.
    """
    # format 2: 8-bit classification + RGB, no GPS time
    header = laspy.LasHeader(point_format=7)
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.classification = labels

    colors = labels_to_colors(labels)
    las.red = colors[:, 0]
    las.green = colors[:, 1]
    las.blue = colors[:, 2]

    las.write(output_path)
    print(f"Wrote {len(points)} points to {output_path}")


# -----Main---------------------------------------------------------------------
def main():
    """Parses CLI arguments and converts the given pickle or .txt file to LAZ."""
    parser = argparse.ArgumentParser(
        description="Convert .p point cloud to LAZ.")
    parser.add_argument(
        "input_path", help="Path to input pickle or .txt (Nx4) file")
    parser.add_argument(
        "-o", "--output", help="Output .laz path (default: same name, .laz)")
    args = parser.parse_args()

    input_path = args.input_path
    ext = os.path.splitext(args.input_path)[1].lower()
    if ext == ".p":
        points, labels = read_pickle(input_path)
    elif ext == ".txt":
        points, labels = read_txt(input_path)
    else:
        print(f"Error: unsupported input '{ext}'. Use .p or .ply.")
        sys.exit(1)

    output_path = args.output or os.path.splitext(input_path)[0] + ".laz"
    write_laz(points, labels, output_path)


if __name__ == "__main__":
    main()
