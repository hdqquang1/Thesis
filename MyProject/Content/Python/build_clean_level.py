# build_clean_level.py
# Creates (or loads, if it exists) a fresh empty level at /Game/Maps/AnnotationMap
# and sets the VRGameMode as its default. Run once, then run build_flat_vr_scene.py
# to spawn the point cloud + ground + nav + pawn + lighting into it.
#
# Run from: Tools -> Execute Python Script
#   (or, in the Output Log: py build_clean_level.py)
# Requires plugins: Python Editor Script Plugin + Editor Scripting Utilities

import unreal

# --- CONFIG ---------------------------------------------------------
LEVEL_PATH = "/Game/Maps/AnnotationMap"
GAME_MODE  = "/Game/VRTemplate/Blueprints/VRGameMode"
# --------------------------------------------------------------------

les    = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues    = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
assets = unreal.EditorAssetLibrary


def log(msg):
    unreal.log(f"[Clean Level] {msg}")


# 1. Create the level, or load it if it already exists.
if assets.does_asset_exist(LEVEL_PATH):
    log(f"Level already exists at {LEVEL_PATH}; loading it.")
    les.load_level(LEVEL_PATH)
else:
    created = les.new_level(LEVEL_PATH)
    assert created, f"Failed to create new level at {LEVEL_PATH}"
    log(f"Created new empty level at {LEVEL_PATH}.")

# 2. Set the WorldSettings DefaultGameMode to VRGameMode so the VR pawn
#    spawns correctly when you press Play.
gm_class = assets.load_blueprint_class(GAME_MODE)
assert gm_class, f"Could not load GameMode blueprint at {GAME_MODE}"

world = ues.get_editor_world()
ws    = world.get_world_settings()
ws.set_editor_property("default_game_mode", gm_class)
log(f"DefaultGameMode set to {GAME_MODE}.")

# 3. Save.
saved = les.save_current_level()
log(f"Level saved: {saved}.")
log("Next: run `py build_flat_vr_scene.py` to populate the level.")
