"""Converts a labelled point cloud to LAZ

Accepts either:
  - a pickle .p file  (Nx4: x, y, z, label)
  - an ASCII .ply     (x y z r g b, label-as-colour)
"""


# -----Imports------------------------------------------------------------------
import sys
import os
import pickle
import argparse
import numpy as np
import laspy

from convert_p import COLOR_MAP


# -----Functions----------------------------------------------------------------
def load_from_pickle(path):
    """Loads points and labels from an Nx4 pickle file.

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


def load_from_ply(path):
    """Loads points and labels from an ASCII x y z r g b PLY file.

    Labels are recovered by reversing COLOR_MAP: each point's RGB
    colour is looked up against the map to recover its original
    classification. Colours not found in COLOR_MAP are set to 31
    (unmapped).

    Args:
        path: Path to the ASCII PLY file.

    Returns:
        A tuple of (points, labels): points is an (N, 3) float32
        array, labels is an (N,) uint8 array.
    """
    with open(path, "r") as f:
        n_header = 0
        for line in f:
            n_header += 1
            if line.strip() == "end_header":
                break
    raw = np.loadtxt(path, skiprows=n_header)
    points = raw[:, :3].astype(np.float32)
    colors = raw[:, 3:6].astype(np.int64)

    # Reverse the colour map: build a lookup from packed RGB -> label.
    packed = (colors[:, 0] << 16) | (colors[:, 1] << 8) | colors[:, 2]
    labels = np.full(len(points), 31, dtype=np.uint8)  # 31 = unmapped
    for label, (r, g, b) in COLOR_MAP.items():
        key = (r << 16) | (g << 8) | b
        labels[packed == key] = label

    n_unmapped = int((labels == 31).sum())
    if n_unmapped:
        print(f"Warning: {n_unmapped} points had colours not in COLOR_MAP "
              f"(set to classification 31).")
    return points, labels


def write_laz(points, labels, out_path):
    """Writes points and classification labels to a LAZ file.

    Args:
        points: (N, 3) array of x, y, z coordinates.
        labels: (N,) array of classification labels.
        out_path: Path to write the .laz file to.
    """
    # format 6: full 8-bit classification, no RGB
    header = laspy.LasHeader(point_format=6)
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.classification = labels
    las.write(out_path)
    print(f"Wrote {len(points)} points to {out_path}")


# -----Main---------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert .p or .ply point cloud to LAZ.")
    parser.add_argument(
        "input_file", help="Path to input .p (Nx4) or .ply file")
    parser.add_argument(
         "-o", "--output", help="Output .laz path (default: same name, .laz)")
    args = parser.parse_args()

    ext = os.path.splitext(args.input_file)[1].lower()
    if ext == ".p":
        points, labels = load_from_pickle(args.input_file)
    elif ext == ".ply":
        points, labels = load_from_ply(args.input_file)
    else:
        print(f"Error: unsupported input '{ext}'. Use .p or .ply.")
        sys.exit(1)

    out_path = args.output or os.path.splitext(args.input_file)[0] + ".laz"
    write_laz(points, labels, out_path)
