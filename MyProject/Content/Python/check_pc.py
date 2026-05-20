import unreal

cloud = unreal.EditorAssetLibrary.load_asset(
    "/Game/PointClouds/labelled_native_forest_2_flatten"
)

full = cloud.get_bounds()
center = unreal.Vector(
    (full.min.x + full.max.x) * 0.5,
    (full.min.y + full.max.y) * 0.5,
    (full.min.z + full.max.z) * 0.5,
)
extent = unreal.Vector(50, 50, 50)   # half-size = 1m cube total

# Args: (center, extent, visible_only, return_world_space)
points = cloud.get_points_in_box_as_copies(center, extent, False, False)
print(f"Got {len(points)} points in 1m sample")

if points:
    p = points[0]
    print("Type:", type(p).__name__)
    print("Attributes:", [x for x in dir(p) if not x.startswith('_')])
    for attr in ('location', 'color', 'classification_id', 'normal', 'id'):
        if hasattr(p, attr):
            print(f"  {attr}:", getattr(p, attr))