import open3d as o3d
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python downsample.py <file.p>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = input_path.replace(".ply", "_downsampled.ply")

    input_pc = o3d.io.read_point_cloud(input_path)
    output_pc = input_pc.voxel_down_sample(voxel_size=0.1)
    print(len(output_pc.points))
    o3d.visualization.draw_geometries([output_pc])

    # o3d.io.write_point_cloud(output_path, output_pc)
