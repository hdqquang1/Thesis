"""Exports a labelled LAZ point cloud imported into UE5 to canonical numpy 
arrays and UE5 asset.
"""


# -----Imports------------------------------------------------------------------
import os
import time
import numpy as np
import unreal


# -----Constants------------------------------------------------------------------
ASSET_NAMES = ["HQPLR118V1_cleaned", "native_forest_2"]
DEST_PATH = "/Game/PointClouds"

COLOR_MAP = {
    0: (0, 255, 0),      # Green  - Foliage
    1: (255, 0, 0),      # Red    - Stem
    2: (0, 0, 255),      # Blue   - Ground
    3: (0, 255, 255),    # Cyan   - Undergrowth
}


# -----Functions----------------------------------------------------------------
def _wait_for_import(asset, poll_interval=0.5,
                     stable_checks=3, timeout=60):
    """Point insertion runs on a background thread after import_asset_tasks()
    returns. Poll until the count holds steady across a few checks before trusting it.
    """
    last_count = -1
    stable = 0
    start = time.time()
    while time.time() - start < timeout:
        count = asset.get_num_points()
        if count == last_count:
            stable += 1
            if stable >= stable_checks:
                return count
        else:
            stable = 0
            last_count = count
        time.sleep(poll_interval)
    return last_count


def export(asset_name):
    laz_path = f"N:/Thesis/data/raw/{asset_name}.laz"
    output_dir = f"N:/Thesis/data/{asset_name}/canonical"
    points_filename = os.path.join(output_dir, "points_ue.npy")
    labels_filename = os.path.join(output_dir, "labels.npy")

    if not os.path.isfile(laz_path):
        raise RuntimeError("Source file not found: {}".format(laz_path))

    unreal.log("Importing '{}' as '{}'...".format(laz_path, asset_name))

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", laz_path)
    task.set_editor_property("destination_path", DEST_PATH)
    task.set_editor_property("destination_name", asset_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    imported = list(task.get_editor_property("imported_object_paths") or [])
    if not imported:
        raise RuntimeError("Import produced no assets: {}".format(laz_path))

    asset = unreal.load_object(None, imported[0])

    unreal.EditorAssetLibrary.save_loaded_asset(asset)
    unreal.log("Imported asset saved at '{}'".format(imported[0]))

    unreal.log("Waiting for point insertion to stabilize...")
    stable_count = _wait_for_import(asset)
    unreal.log("Point count stable at {}".format(stable_count))

    os.makedirs(output_dir, exist_ok=True)
    points = asset.get_points_as_copies(False)
    num_points = len(points)
    unreal.log("Extracting {} points and colors...".format(num_points))

    points_array = np.zeros((num_points, 3), dtype=np.float32)
    colors_array = np.zeros((num_points, 3), dtype=np.int64)
    with unreal.ScopedSlowTask(num_points, "Extracting points and colors") as slow_task:
        slow_task.make_dialog(True)
        for i, point in enumerate(points):
            if slow_task.should_cancel():
                break
            slow_task.enter_progress_frame(1)
            location = point.location
            points_array[i] = (
                location.get_editor_property("x"),
                location.get_editor_property("y"),
                location.get_editor_property("z"),
            )
            color = point.color
            colors_array[i] = (color.r, color.g, color.b)
    np.save(points_filename, points_array)
    unreal.log("Saved points array to '{}'".format(points_filename))

    # Reverse the colour map: build a lookup from packed RGB to label.
    unreal.log("Assigning labels from colors...")
    packed = (colors_array[:, 0] << 16) | (
        colors_array[:, 1] << 8) | colors_array[:, 2]
    labels_array = np.full(num_points, 31, dtype=np.uint8)
    with unreal.ScopedSlowTask(len(COLOR_MAP), "Assigning labels from colors") as slow_task:
        slow_task.make_dialog(True)
        for label, (r, g, b) in COLOR_MAP.items():
            if slow_task.should_cancel():
                break
            slow_task.enter_progress_frame(1)
            key = (r << 16) | (g << 8) | b
            labels_array[packed == key] = label

    unmatched = int(np.count_nonzero(labels_array == 31))
    if unmatched:
        unreal.log_warning(
            "{} points did not match any color in COLOR_MAP".format(unmatched))

    np.save(labels_filename, labels_array)
    unreal.log("Saved labels array to '{}'".format(labels_filename))
    unreal.log("Done with '{}'.".format(asset_name))


# -----Main---------------------------------------------------------------------
def main():
    for asset_name in ASSET_NAMES:
        export(asset_name)
    unreal.log("All exports done.")


if __name__ == "__main__":
    main()
