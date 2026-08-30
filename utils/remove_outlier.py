import open3d as o3d
import argparse

from convert_to_laz import (
    read_laz,
    write_laz
)


# Copied from Open3D document
def display_inlier_outlier(cloud, ind):
    inlier_cloud = cloud.select_by_index(ind)
    outlier_cloud = cloud.select_by_index(ind, invert=True)

    print("Showing outliers (red) and inliers (gray): ")
    outlier_cloud.paint_uniform_color([1, 0, 0])
    inlier_cloud.paint_uniform_color([0.8, 0.8, 0.8])
    o3d.visualization.draw_geometries([inlier_cloud, outlier_cloud],
                                      zoom=0.3412,
                                      front=[0.4257, -0.2125, -0.8795],
                                      lookat=[2.6172, 2.0475, 1.532],
                                      up=[-0.0694, -0.9768, 0.2024])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove outliers in a point cloud"
    )
    parser.add_argument(
        "input_path", help="Path to input .laz file"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save the cleaned file instead of displaying it for checking")
    args = parser.parse_args()

    input_path = args.input_path
    output_path = input_path.replace(".laz", "_cleaned.laz")

    # Load point cloud
    points, labels, _, _, _ = read_laz(input_path)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # Remove outliers
    # _, ind = pcd.remove_statistical_outlier(nb_neighbors=10, std_ratio=2.0)
    _, ind = pcd.remove_radius_outlier(nb_points=10, radius=0.5)

    if not args.save:
        # Display to check
        display_inlier_outlier(pcd, ind)
        return

    # Write cleaned file
    points_cleaned = points[ind]
    labels_cleaned = labels[ind]
    assert len(points_cleaned) == len(labels_cleaned)
    write_laz(points_cleaned, labels_cleaned, output_path)
    print(
        f"Removed {len(points) - len(points_cleaned)} points from {len(points)}.")


if __name__ == "__main__":
    main()
