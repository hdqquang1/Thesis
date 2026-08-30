"""Downsample a point cloud using voxel downsampling while keeping the original 
classification
"""


# -----Imports------------------------------------------------------------------
import numpy as np
import argparse
from convert_to_laz import (
    read_laz,
    write_laz
)


# -----Functions----------------------------------------------------------------
def get_density(points: np.ndarray) -> float:
    """Calculates density of the point cloud

    Args:
        points: numpy array of points

    Returns:
        Density of point cloud in points/m³
    """
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    volume = np.prod(bbox_max - bbox_min)
    return len(points) / volume


# -----Main---------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Downsample a LAZ point cloud, retaining exact classification"
    )
    parser.add_argument(
        "input_path", help="Path to input LAZ file"
    )
    args = parser.parse_args()

    input_path = args.input_path
    output_path = input_path.replace(".laz", "_downsampled.laz")
    voxel_size = 0.2

    points, classification, red, green, blue = read_laz(input_path)

    # Pick one real point per voxel (no averaging), so position and
    # classification always stay correctly paired.
    voxel_indices = np.floor(points / voxel_size).astype(np.int64)
    _, representative_indices = np.unique(
        voxel_indices, axis=0, return_index=True)

    output_points = points[representative_indices]
    output_classification = classification[representative_indices]

    print(
        f"Input has size {len(points)}, density {get_density(points)} pts/m3")
    print(
        f"Output has size {len(output_points)}, density {get_density(output_points)} pts/m3")

    write_laz(output_points, output_classification, output_path)
    print(f"Wrote {len(output_points)} points to {output_path}")


if __name__ == "__main__":
    main()
