"""Flatten point cloud surface by normalizing Z coordinates per grid cell."""

import sys
import os
import pickle
import numpy as np


def flatten_surface(pickle_path, grid_resolution=1):
    """
    Flatten surface by normalizing Z per grid cell.
    
    The lowest point in each (x,y) grid cell becomes ground level (z=0),
    and all other points in that cell are offset by the same amount.

    Args:
        pickle_path: Path to the pickle file to flatten
        grid_resolution: Grid cell size in meters (default: 1m)
    """
    # Load data
    with open(pickle_path, 'rb') as f:
        data = pickle.load(f)
    
    # Separate coordinates and labels
    points = data[:, :3].astype(np.float32)
    labels = data[:, 3].astype(np.int64)
    
    # Discretize x,y coordinates into grid cells
    x_min, y_min = points[:, 0].min(), points[:, 1].min()
    x_grid = ((points[:, 0] - x_min) / grid_resolution).astype(np.int32)
    y_grid = ((points[:, 1] - y_min) / grid_resolution).astype(np.int32)
    
    # For each grid cell, find the minimum z value
    grid_cells = {}
    for i in range(len(points)):
        cell_key = (x_grid[i], y_grid[i])
        z_val = points[i, 2]
        if cell_key not in grid_cells:
            grid_cells[cell_key] = z_val
        else:
            grid_cells[cell_key] = min(grid_cells[cell_key], z_val)
    
    # For each point, get its cell's minimum z (ground at that cell)
    per_point_min = np.fromiter(
        (grid_cells[(x_grid[i], y_grid[i])] for i in range(len(points))),
        dtype=np.float32,
        count=len(points)
    )

    # Shift each point's z by its cell's minimum so cell ground -> 0
    points_flat = points.copy()
    points_flat[:, 2] = points[:, 2] - per_point_min
    
    # Save result
    flattened_data = np.hstack((points_flat, labels.reshape(-1, 1)))
    
    base, ext = os.path.splitext(pickle_path)
    output_path = f"{base}_flatten{ext}"
    
    with open(output_path, 'wb') as f:
        pickle.dump(flattened_data, f)
    
    print(f"Flattened surface saved to: {output_path}")
    print(f"Grid resolution: {grid_resolution}m")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python flatten.py <file.p> [grid_resolution]")
        sys.exit(1)
    
    pickle_path = sys.argv[1]
    grid_res = float(sys.argv[2]) if len(sys.argv) > 2 else 1
    flatten_surface(pickle_path, grid_res)