"""Downsample a point cloud using voxel downsampling while keeping the original 
classification
"""


# -----Imports------------------------------------------------------------------
import numpy as np
import sys
import argparse
import laspy


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
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Downsample a LAZ point cloud, retaining exact classification"
    )
    parser.add_argument(
        "input_file", help="Path to input LAZ file"
    )

    input_path = sys.argv[1]
    output_path = input_path.replace(".laz", "_downsampled.laz")
    voxel_size = 0.2

    las_in = laspy.read(input_path)
    points = np.vstack((las_in.x, las_in.y, las_in.z)).transpose()
    classification = np.asarray(las_in.classification)

    # Pick one real point per voxel (no averaging), so position and
    # classification always stay correctly paired.
    voxel_indices = np.floor(points / voxel_size).astype(np.int64)
    _, representative_indices = np.unique(
        voxel_indices, axis=0, return_index=True)

    out_points = points[representative_indices]
    out_classification = classification[representative_indices]

    print(
        f"Input has size {len(points)}, density {get_density(points)} pts/m3")
    print(
        f"Output has size {len(out_points)}, density {get_density(out_points)} pts/m3")

    header = laspy.LasHeader(point_format=6)
    las_out = laspy.LasData(header)
    las_out.x = out_points[:, 0]
    las_out.y = out_points[:, 1]
    las_out.z = out_points[:, 2]
    las_out.classification = out_classification
    las_out.write(output_path)
    print(f"Wrote {len(out_points)} points to {output_path}")
