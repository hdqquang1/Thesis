"""Shared Open3D viewer for the utils scripts."""

# -----Imports------------------------------------------------------------------
import open3d as o3d


# -----Functions----------------------------------------------------------------
def show_clouds(clouds):
    """Shows point clouds in one window, small points, near-orthographic view.

    Args:
        clouds: List of Open3D geometries to draw together.
    """
    viewer = o3d.visualization.Visualizer()
    viewer.create_window()
    for cloud in clouds:
        viewer.add_geometry(cloud)
    viewer.get_view_control().change_field_of_view(step=-90)
    viewer.get_render_option().point_size = 1.0
    viewer.run()
    viewer.destroy_window()
