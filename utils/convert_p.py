"""Convert pickle point cloud files to other formats with color mapping."""

import sys
import os
import pickle
import argparse
import numpy as np
from tqdm import tqdm


# Color mapping: label -> RGB tuple
COLOR_MAP = {
    0: (0, 255, 0),      # Green - Foliage
    1: (255, 0, 0),      # Red - Stem
    2: (0, 0, 255),      # Blue - Ground
    3: (0, 255, 255),    # Cyan - Undergrowth
}
DEFAULT_COLOR = (255, 255, 255)  # White for unmapped labels

def convert_pickle(pickle_path, options='txt'):
    """
    Convert pickle file to PLY format with color-coded labels.
    
    Args:
        pickle_path: Path to input pickle file (Nx3 or Nx4 format)
        options: Output format ('txt' for .txt, 'ply' for PLY)
    """
    if not os.path.exists(pickle_path):
        print(f"Error: Pickle file not found at {pickle_path}")
        sys.exit(1)
    
    # Load pickle data
    with open(pickle_path, 'rb') as f:
        data = pickle.load(f)
    
    # Extract coordinates and labels
    points_data = data[:, :3].astype(np.float32)

    if data.shape[1] == 4:
        labels_data = data[:, 3].astype(np.int32)
    else:
        # Default to label 2 (ground) if no labels present
        labels_data = np.ones(data.shape[0]).astype(np.int32) * 2
    
    # Total number of vertices
    num_vertices = points_data.shape[0]
    
    # Map labels to RGB colors
    # Create an array of default colors
    colors_rgb = np.full((num_vertices, 3), DEFAULT_COLOR, dtype=np.uint8)
    
    # Apply specific colors based on the map
    for label, color in tqdm(COLOR_MAP.items(), desc="Mapping labels", unit="label"):
        # Find indices where the label matches the key
        indices = np.where(labels_data == label)[0]
        # Set the color for those indices
        colors_rgb[indices] = color
    
    # Combine coordinates and colors: (N, 6) = (x, y, z, r, g, b)
    data_combined = np.hstack((points_data, colors_rgb)).astype(object)
    
    # Write PLY file
    if options == 'txt':
        output_path = os.path.splitext(pickle_path)[0] + '.txt'
        with open(output_path, 'w') as f:
            for row in tqdm(data_combined, desc="Writing TXT", unit="points", total=num_vertices):
                x, y, z, r, g, b = row
                f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")
    elif options == 'ply':
        output_path = os.path.splitext(pickle_path)[0] + '.ply'
        try:
            with open(output_path, 'w') as f:
                # Write header
                f.write("ply\n")
                f.write("format ascii 1.0\n")
                f.write(f"element vertex {num_vertices}\n")
                f.write("property float x\n")
                f.write("property float y\n")
                f.write("property float z\n")
                f.write("property uchar diffuse_red\n")
                f.write("property uchar diffuse_green\n")
                f.write("property uchar diffuse_blue\n")
                f.write("end_header\n")
                
                # Write vertex data
                for row in tqdm(data_combined, desc="Writing PLY", unit="points", total=num_vertices):
                    x, y, z, r, g, b = row
                    f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")
            
            print(f"Successfully wrote {num_vertices} vertices to {output_path}")
        
        except Exception as e:
            print(f"An error occurred while writing the PLY file: {e}")
    else:
        print(f"Error: Unsupported output format '{options}'. Use 'txt' or 'ply'.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert pickle point cloud files to other formats with color mapping."
    )
    parser.add_argument(
        "input_file",
        help="Path to input pickle file (Nx3 or Nx4 format)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["txt", "ply"],
        default="txt",
        help="Output format (default: txt)"
    )
    
    args = parser.parse_args()
    convert_pickle(args.input_file, options=args.format)