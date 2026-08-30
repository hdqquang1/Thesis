"""Tests if imports of the same point cloud is determinism.
"""
import unreal
import numpy as np


TEST_DIR = "/Game/TestAssets"


def _points_array(asset):
    points = asset.get_points_as_copies(False)
    return np.array(
        [[p.location.get_editor_property("x"),
          p.location.get_editor_property("y"),
          p.location.get_editor_property("z")] for p in points],
        dtype=np.float64,
    )


if __name__ == "__main__":
    asset_paths = sorted(unreal.EditorAssetLibrary.list_assets(
        TEST_DIR, recursive=False, include_folder=False))
    if not asset_paths:
        raise RuntimeError("No assets found in {}".format(TEST_DIR))

    print("Found {} assets in {}:".format(len(asset_paths), TEST_DIR))
    for p in asset_paths:
        print("  ", p)

    baseline_path = None
    baseline = None
    all_match = True

    for path in asset_paths:
        obj = unreal.load_object(None, path)
        arr = _points_array(obj)
        print("{}: {} points".format(path, len(arr)))

        if baseline is None:
            baseline_path, baseline = path, arr
            continue

        if arr.shape != baseline.shape:
            print("  MISMATCH shape vs {}: {} vs {}".format(
                baseline_path, arr.shape, baseline.shape))
            all_match = False
            continue

        if np.array_equal(arr, baseline):
            print("  matches {} exactly".format(baseline_path))
        else:
            diff_count = int(np.sum(np.any(arr != baseline, axis=1)))
            print("  DIFFERS from {} at {} of {} points".format(
                baseline_path, diff_count, len(arr)))
            all_match = False

    print()
    print("RESULT:", "order is stable across all imports" if all_match
          else "order is NOT stable -- import is nondeterministic")
