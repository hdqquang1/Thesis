"""Remove labels from a labelled point cloud pickle file."""

import os
import sys
import pickle
import argparse
import numpy as np


def unlabel_point_cloud(pickle_path):
    """
    Remove label column from a point cloud pickle file.

    Expected input shape: Nx4 (x, y, z, label)
    Output shape: Nx3 (x, y, z)

    Args:
        pickle_path: Path to the input pickle file

    Returns:
        Path to the output pickle file
    """
    if not os.path.exists(pickle_path):
        print(f"Error: Input file not found: {pickle_path}")
        sys.exit(1)

    with open(pickle_path, "rb") as f:
        data = pickle.load(f)

    if not isinstance(data, np.ndarray):
        print("Error: Pickle content is not a NumPy array.")
        sys.exit(1)

    if data.ndim != 2 or data.shape[1] < 3:
        print(f"Error: Unexpected array shape {data.shape}. Expected Nx4 or Nx3.")
        sys.exit(1)

    # Keep only xyz coordinates.
    unlabelled_data = data[:, :3]

    base_name = os.path.splitext(pickle_path)[0]
    output_path = f"{base_name}_unlabelled.p"

    with open(output_path, "wb") as f:
        pickle.dump(unlabelled_data, f)

    print(f"Saved unlabelled point cloud to: {output_path}")
    print(f"Input shape: {data.shape} -> Output shape: {unlabelled_data.shape}")

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remove labels from a point cloud pickle file and save as <input_file>_unlabelled.p"
    )
    parser.add_argument("input_file", help="Path to input pickle file")

    args = parser.parse_args()
    unlabel_point_cloud(args.input_file)
