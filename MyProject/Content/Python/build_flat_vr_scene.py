# build_flat_vr_scene.py
# Run from: Tools -> Execute Python Script (or Output Log: py build_flat_vr_scene.py)
# Requires plugins: "Python Editor Script Plugin" + "Editor Scripting Utilities"

import unreal

# --- CONFIG: edit these for your project --------------
POINT_CLOUD_ASSET = "/Game/PointClouds/labelled_native_forest_2_flatten"
VR_PAWN_CLASS     = "/Game/VRTemplate/Blueprints/VRPawn"
GROUND_MARGIN     = 1.10   # cube covers 110% of cloud XY extent
GROUND_THICKNESS  = 20.0   # cm
PAWN_Z_OFFSET     = 0      # cm above ground top to avoid interpenetration
USE_PERCENTILE_Z  = False  # True = ignore outlier low points (robust), False = absolute min

# Lighting / sky
SUN_PITCH         = -45.0  # degrees; -90 = noon overhead, 0 = horizon
SUN_YAW           = 30.0
SUN_INTENSITY     = 10.0   # lux-equivalent when atmosphere_sun_light=True
SUN_CAST_SHADOWS  = False  # cheap on Quest 3S; flip on for final renders
FOG_DENSITY       = 0.02   # 0.02 = engine default; lower = clearer
# -------------------------------------------------------

eas   = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
asset = unreal.EditorAssetLibrary

def log(msg): unreal.log(f"[VR Pipeline] {msg}")

# 0. Purge actors from previous runs so the script is idempotent.
# Matches by label prefix so it also cleans up earlier "_Auto" naming.
MANAGED_LABELS = (
    "PointCloud", "GroundCollider", "NavBounds", "VRPawn",
    "SkyAtmosphere", "SunLight", "SkyLight", "HeightFog",
)
purged = 0
for a in eas.get_all_level_actors():
    label = a.get_actor_label()
    if any(label == base or label.startswith(base + "_") or label.startswith(base + "Auto") for base in MANAGED_LABELS):
        eas.destroy_actor(a)
        purged += 1
log(f"Purged {purged} actor(s) from previous runs.")

# 0b. Spawn the sky/lighting rig. This runs before the cloud so the scene
# is lit while the (expensive) cloud is registering. Idempotent via labels.
sky_atm = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
sky_atm.set_actor_label("SkyAtmosphere")

sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 1000))
sun.set_actor_label("SunLight")
sun.set_actor_rotation(unreal.Rotator(0.0, SUN_PITCH, SUN_YAW), False)
sun_comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
sun_comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
sun_comp.set_editor_property("atmosphere_sun_light", True)
sun_comp.set_editor_property("intensity", SUN_INTENSITY)
sun_comp.set_editor_property("cast_shadows", SUN_CAST_SHADOWS)

sky_light = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 200))
sky_light.set_actor_label("SkyLight")
slc = sky_light.get_component_by_class(unreal.SkyLightComponent)
slc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
slc.set_editor_property("real_time_capture", True)

fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
fog.set_actor_label("HeightFog")
fog_comp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
fog_comp.set_editor_property("fog_density", FOG_DENSITY)

log("Spawned sky atmosphere, sun, sky light, and height fog.")

# 1. Load the point cloud asset
cloud = asset.load_asset(POINT_CLOUD_ASSET)
assert cloud, f"Could not load point cloud at {POINT_CLOUD_ASSET}"

# 2. Spawn the cloud actor at origin
cloud_actor = eas.spawn_actor_from_class(
    unreal.LidarPointCloudActor, unreal.Vector(0, 0, 0)
)
cloud_actor.set_actor_label("PointCloud")
pcc = cloud_actor.get_editor_property('point_cloud_component')
pcc.set_point_cloud(cloud)
pcc.set_editor_property('point_size', 0.2)
pcc.set_point_shape(unreal.LidarPointCloudSpriteShape.CIRCLE)
# pcc.set_editor_property('point_size_bias', 0.03)
# pcc.set_editor_property('scaling_method', unreal.LidarPointCloudScalingMethod.FIXED_SCREEN_SIZE)
# pcc.set_editor_property('intensity_influence', 0.4)

# 3. Read bounds from the asset
bounds = cloud.get_bounds()              # FBox in the cloud's local space
bmin, bmax = bounds.min, bounds.max
size_x = bmax.x - bmin.x
size_y = bmax.y - bmin.y
center_x = (bmin.x + bmax.x) * 0.5
center_y = (bmin.y + bmax.y) * 0.5
ground_z = bmin.z  # absolute lowest point

# Optional: robust ground estimate via percentile (ignores noise below true ground).
# The plugin's per-point access is slow for 20M points; if you want this,
# use the 'Extract Points in Box' API on a thin slab near bmin.z and
# take the median. For a flat forest, bmin.z is fine.

# 4. Recenter cloud so its XY midpoint sits on world origin
cloud_actor.set_actor_location(
    unreal.Vector(-center_x, -center_y, 0), False, True
)

# 5. Spawn the invisible ground cube
cube_mesh = asset.load_asset("/Engine/BasicShapes/Cube.Cube")
cube_top_z = ground_z
cube_center_z = cube_top_z - GROUND_THICKNESS * 0.5
ground = eas.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, cube_center_z)
)
ground.set_actor_location(unreal.Vector(0, 0, cube_center_z), False, True)
ground.set_actor_label("GroundCollider")
smc = ground.static_mesh_component
smc.set_static_mesh(cube_mesh)
# Engine cube is 100cm; convert desired world size to scale
ground.set_actor_scale3d(unreal.Vector(
    (size_x * GROUND_MARGIN) / 100.0,
    (size_y * GROUND_MARGIN) / 100.0,
    GROUND_THICKNESS / 100.0,
))
smc.set_visibility(False)   # invisible in editor + game, collision still active

# 6. NavMeshBoundsVolume over the same footprint
# NavMeshBoundsVolume's default brush is 200cm; scale accordingly.
nav = eas.spawn_actor_from_class(
    unreal.NavMeshBoundsVolume, unreal.Vector(0, 0, cube_top_z + 150)
)
nav.set_actor_location(unreal.Vector(0, 0, cube_top_z + 150), False, True)
nav.set_actor_label("NavBounds")
nav.set_actor_scale3d(unreal.Vector(
    (size_x * GROUND_MARGIN) / 200.0,
    (size_y * GROUND_MARGIN) / 200.0,
    3.0,   # 6m vertical - enough for standing VR pawn
))

# 7. Spawn the VR pawn at world origin, just above the ground
pawn_class = asset.load_blueprint_class(VR_PAWN_CLASS)
pawn = eas.spawn_actor_from_class(
    pawn_class, unreal.Vector(0, 0, cube_top_z + PAWN_Z_OFFSET)
)
pawn.set_actor_location(unreal.Vector(0, 0, cube_top_z + PAWN_Z_OFFSET), False, True)
pawn.set_actor_label("VRPawn")

# 8. Kick a nav rebuild (auto-build is usually on; this nudges it)
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_invalidate_viewports()

log(f"Done. ground_z={ground_z:.1f}cm  size=({size_x:.0f} x {size_y:.0f})cm")
log("Open Project Settings -> Navigation Mesh to tune AgentRadius/Height/MaxSlope.")
