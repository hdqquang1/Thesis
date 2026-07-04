"""Convert a labelled point cloud to LAZ, storing the class in the LAS classification field.

Accepts either:
  - a pickle .p file  (Nx4: x, y, z, label)         <- recommended, true labels
  - an ASCII .ply     (x y z r g b, label-as-colour) <- label recovered from COLOR_MAP

The four-class label (0=foliage, 1=stem, 2=ground, 3=undergrowth) is written to the
LAS `classification` field, NOT to RGB. This is the master/archival format and the
UE5 LidarPointCloud import source.
"""

import sys
import os
import pickle
import argparse
import numpy as np
import laspy


# Same mapping as utils/convert_p.py, used to reverse PLY colours back to labels.
COLOR_MAP = {
    0: (0, 255, 0),      # Green  - Foliage
    1: (255, 0, 0),      # Red    - Stem
    2: (0, 0, 255),      # Blue   - Ground
    3: (0, 255, 255),    # Cyan   - Undergrowth
}


def load_from_pickle(path):
    """Return (points Nx3 float32, labels N uint8) from an Nx4 pickle."""
    data = pickle.load(open(path, "rb"))
    points = data[:, :3].astype(np.float32)
    labels = data[:, 3].astype(np.uint8)
    return points, labels


def load_from_ply(path):
    """Return (points Nx3 float32, labels N uint8) from an ASCII x y z r g b PLY."""
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
    labels = np.full(len(points), 255, dtype=np.uint8)  # 255 = unmapped
    for label, (r, g, b) in COLOR_MAP.items():
        key = (r << 16) | (g << 8) | b
        labels[packed == key] = label

    n_unmapped = int((labels == 255).sum())
    if n_unmapped:
        print(f"Warning: {n_unmapped} points had colours not in COLOR_MAP "
              f"(set to classification 255).")
    return points, labels


def write_laz(points, labels, out_path):
    header = laspy.LasHeader(point_format=6)  # format 6: full 8-bit classification, no RGB
    las = laspy.LasData(header)
    las.x = points[:, 0]
    las.y = points[:, 1]
    las.z = points[:, 2]
    las.classification = labels
    las.write(out_path)
    print(f"Wrote {len(points)} points to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Convert .p or .ply point cloud to LAZ.")
    parser.add_argument("input_file", help="Path to input .p (Nx4) or .ply file")
    parser.add_argument("-o", "--output", help="Output .laz path (default: same name, .laz)")
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


if __name__ == "__main__":
    main()
