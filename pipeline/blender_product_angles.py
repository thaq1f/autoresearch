"""
Blender script: Export FAST solid/workbench renders for AI texturing.

NO Cycles. NO materials. NO slow rendering.
Exports structural data that AI uses to apply photorealistic textures:

  1. Solid view — clean geometry with basic shading (for flux-kontext)
  2. Depth pass — normalized Z-depth (for ControlNet depth)
  3. Outline pass — edge/silhouette lines (for ControlNet canny)

Each takes seconds, not minutes. The AI handles all styling.

Usage:
  /Applications/Blender.app/Contents/MacOS/Blender \
    --background /Users/thaqif/Projects/limpahan/LE-v3.blend \
    --python pipeline/blender_product_angles.py -- \
    --output pipeline/refs

Options:
  --output DIR       Output directory (default: pipeline/refs)
  --resolution W H   Resolution (default: 1920 1080)
  --preset PRESET    product (7 angles) or turntable (12 angles)
  --passes PASSES    Comma-separated: solid,depth,outline (default: solid)
"""

import bpy
import math
import sys
from pathlib import Path
from mathutils import Vector


def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", default="pipeline/refs")
    parser.add_argument("--resolution", "-r", nargs=2, type=int, default=[1920, 1080])
    parser.add_argument("--preset", "-p", default="product",
                       choices=["product", "turntable", "single"])
    parser.add_argument("--passes", default="solid",
                       help="Comma-separated: solid,depth,outline (default: solid)")
    parser.add_argument("--azimuth", type=float, default=45)
    parser.add_argument("--elevation", type=float, default=25)
    return parser.parse_args(argv)


# Product photography angles — 50mm standard lens
# (name, azimuth_deg, elevation_deg, focal_mm, distance_multiplier)
PRODUCT_SHOTS = [
    ("01_hero_3quarter",    45,   25,  50, 1.4),
    ("02_front",             0,   12,  50, 1.4),
    ("03_rear",            180,   12,  50, 1.4),
    ("04_left_profile",    -90,   10,  50, 1.4),
    ("05_right_profile",    90,   10,  50, 1.4),
    ("06_high_overview",    35,   55,  35, 1.3),
    ("07_low_dramatic",     25,    5,  35, 1.3),
]

TURNTABLE_SHOTS = [
    (f"turn_{int(a):03d}deg", a, 25, 50, 1.4)
    for a in range(0, 360, 30)
]


def get_model_bounds():
    min_co = Vector((float("inf"),) * 3)
    max_co = Vector((float("-inf"),) * 3)
    count = 0
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.visible_get():
            for corner in obj.bound_box:
                wc = obj.matrix_world @ Vector(corner)
                for i in range(3):
                    min_co[i] = min(min_co[i], wc[i])
                    max_co[i] = max(max_co[i], wc[i])
            count += 1
    if count == 0:
        return Vector((0, 0, 0)), 10.0
    center = (min_co + max_co) / 2
    diagonal = (max_co - min_co).length
    dims = max_co - min_co
    print(f"  Model: {count} objects, {dims.x:.1f} x {dims.y:.1f} x {dims.z:.1f}")
    return center, diagonal


def position_camera(center, diagonal, az_deg, el_deg, focal_mm, dist_mult):
    cam = bpy.data.objects.get("ProductCam")
    if cam is None:
        cam_data = bpy.data.cameras.new("ProductCam")
        cam = bpy.data.objects.new("ProductCam", cam_data)
        bpy.context.scene.collection.objects.link(cam)

    cam.constraints.clear()
    if cam.animation_data:
        cam.animation_data_clear()

    bpy.context.scene.camera = cam

    distance = diagonal * dist_mult * (focal_mm / 50.0)
    az = math.radians(az_deg)
    el = math.radians(el_deg)

    cam.location = Vector((
        center.x + distance * math.cos(el) * math.cos(az),
        center.y + distance * math.cos(el) * math.sin(az),
        center.z + distance * math.sin(el),
    ))

    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    cam.data.lens = focal_mm
    cam.data.clip_start = 0.01
    cam.data.clip_end = distance * 20
    cam.data.sensor_width = 36


def go_to_final_frame():
    scene = bpy.context.scene
    scene.frame_set(scene.frame_end)
    print(f"  Frame: {scene.frame_end} (fully assembled)")


def apply_materials():
    """Run the H2 materials script to assign proper colors to each component."""
    import importlib.util
    mat_script = "/Users/thaqif/Projects/limpahan/blender_h2_materials.py"

    try:
        spec = importlib.util.spec_from_file_location("h2_materials", mat_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
        print("  Materials: H2 component colors applied")
    except Exception as e:
        print(f"  WARNING: Could not apply materials: {e}")
        print(f"  Falling back to Workbench solid colors")


def setup_solid_render(args):
    """EEVEE engine with materials — fast but properly colored."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.resolution[0]
    scene.render.resolution_y = args.resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True

    # Plain solid render — geometry only, no fancy materials or lighting
    # AI does ALL the texturing via ControlNet
    scene.render.engine = "BLENDER_WORKBENCH"

    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.single_color = (0.65, 0.65, 0.67)
    shading.show_shadows = True
    shading.shadow_intensity = 0.5
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.cavity_ridge_factor = 0.5
    shading.cavity_valley_factor = 0.8
    shading.show_object_outline = True

    print("  Engine: Workbench (solid clay render)")


def setup_depth_render(args):
    """Render normalized depth pass via compositing nodes."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = args.resolution[0]
    scene.render.resolution_y = args.resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "BW"
    scene.render.film_transparent = False

    # Enable Z pass
    scene.use_nodes = True
    scene.view_layers[0].use_pass_z = True

    tree = scene.node_tree
    tree.nodes.clear()

    rl = tree.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 0)

    normalize = tree.nodes.new("CompositorNodeNormalize")
    normalize.location = (200, 0)

    invert = tree.nodes.new("CompositorNodeInvert")
    invert.location = (400, 0)

    composite = tree.nodes.new("CompositorNodeComposite")
    composite.location = (600, 0)

    tree.links.new(rl.outputs["Depth"], normalize.inputs["Value"])
    tree.links.new(normalize.outputs["Value"], invert.inputs["Color"])
    tree.links.new(invert.outputs["Color"], composite.inputs["Image"])

    print("  Engine: Workbench (depth pass)")


def setup_outline_render(args):
    """Render edge/outline pass using Freestyle."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = args.resolution[0]
    scene.render.resolution_y = args.resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True

    # Black background, white lines
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "SINGLE"
    shading.single_color = (0, 0, 0)
    shading.show_object_outline = True
    shading.object_outline_color = (1, 1, 1)
    shading.show_shadows = False
    shading.show_cavity = False

    print("  Engine: Workbench (outline pass)")


def render_pass(args, shots, pass_name, setup_fn):
    """Render all angles for a specific pass type."""
    out = Path(args.output) / pass_name
    out.mkdir(parents=True, exist_ok=True)

    setup_fn(args)

    center, diagonal = get_model_bounds()

    print(f"\n  Rendering {len(shots)} angles ({pass_name})...")

    for name, az, el, focal, dist in shots:
        position_camera(center, diagonal, az, el, focal, dist)

        filepath = str(out / f"{name}.png")
        bpy.context.scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        print(f"    {name}.png")

    print(f"  Done: {len(shots)} images → {out}/")


def main():
    args = get_args()

    if args.preset == "product":
        shots = PRODUCT_SHOTS
    elif args.preset == "turntable":
        shots = TURNTABLE_SHOTS
    elif args.preset == "single":
        shots = [("single", args.azimuth, args.elevation, 50, 1.4)]

    passes = [p.strip() for p in args.passes.split(",")]
    pass_map = {
        "solid": setup_solid_render,
        "depth": setup_depth_render,
        "outline": setup_outline_render,
    }

    print("\n--- Setup ---")
    go_to_final_frame()

    for pass_name in passes:
        if pass_name not in pass_map:
            print(f"  Unknown pass: {pass_name}, skipping")
            continue
        render_pass(args, shots, pass_name, pass_map[pass_name])

    # Cleanup
    cam = bpy.data.objects.get("ProductCam")
    if cam:
        bpy.data.objects.remove(cam, do_unlink=True)

    total = len(shots) * len(passes)
    print(f"\n--- Complete ---")
    print(f"  {total} renders across {len(passes)} pass(es)")
    print(f"  Output: {args.output}/")
    print(f"\n  Next: run AI styling on the solid pass:")
    print(f"    bash pipeline/batch_product_shots.sh")


if __name__ == "__main__":
    main()
