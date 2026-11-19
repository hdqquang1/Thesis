"""Displays and removes outliers in point cloud."""

# -----Imports------------------------------------------------------------------
import os
import argparse
import open3d as o3d

from convert_to_laz import read_laz, write_laz
from viewer import show_clouds


# -----Functions----------------------------------------------------------------
# Adapted from Open3D tutorial
def display_inlier_outlier(cloud, ind):
    inlier_cloud = cloud.select_by_index(ind)
    outlier_cloud = cloud.select_by_index(ind, invert=True)

    print("Showing outliers (red) and inliers (gray): ")
    outlier_cloud.paint_uniform_color([1, 0, 0])
    inlier_cloud.paint_uniform_color([0.8, 0.8, 0.8])
    show_clouds([inlier_cloud, outlier_cloud])


# -----Main---------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Remove outliers in a point cloud")
    parser.add_argument("input_path", help="Path to input .laz file")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the cleaned file instead of displaying it for checking",
    )
    args = parser.parse_args()

    input_path = args.input_path
    output_path = os.path.splitext(input_path)[0] + "_cleaned.laz"

    # Load point cloud
    points, labels, _, _, _ = read_laz(input_path)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # Remove outliers
    _, ind = pcd.remove_radius_outlier(nb_points=10, radius=0.5)

    if not args.save:
        # Display to check
        display_inlier_outlier(pcd, ind)
        return

    # Write cleaned file
    points_cleaned = points[ind]
    labels_cleaned = labels[ind]
    write_laz(points_cleaned, labels_cleaned, output_path)
    print(f"Removed {len(points) - len(points_cleaned)} points from {len(points)}.")


if __name__ == "__main__":
    main()
