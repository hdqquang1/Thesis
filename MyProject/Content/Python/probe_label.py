# probe_label.py - sanity-check the label-via-color pipeline
import unreal

CLOUD_PATH = "/Game/PointClouds/labelled_native_forest_2_flatten"

INV_COLOR_MAP = {
    (0,   255, 0  ): "Foliage",
    (255, 0,   0  ): "Stem",
    (0,   0,   255): "Ground",
    (0,   255, 255): "Undergrowth",
}

def label_for(point):
    if point is None:
        return "<no hit>"
    rgb = (point.color.r, point.color.g, point.color.b)
    return INV_COLOR_MAP.get(rgb, f"<unknown rgb={rgb}>")

cloud = unreal.EditorAssetLibrary.load_asset(CLOUD_PATH)
b = cloud.get_bounds()
cx = (b.min.x + b.max.x) * 0.5
cy = (b.min.y + b.max.y) * 0.5

# Ray: start above the canopy, fire straight down 100m
origin    = unreal.Vector(cx, cy, b.max.z + 100)
direction = unreal.Vector(0, 0, -1) * 10000

hit = cloud.line_trace_single(origin, direction, 5.0, False)
print(f"Hit point:   {hit}")
print(f"Label:       {label_for(hit)}")
if hit:
    print(f"Location:    {hit.location}")
    print(f"Color RGB:   ({hit.color.r}, {hit.color.g}, {hit.color.b})")