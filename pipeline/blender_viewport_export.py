"""
Blender script: Export product photography camera angles.

Renders multiple camera angles of the model using EEVEE (fast, seconds each).
These serve as geometry-accurate references for AI style transfer.

The AI doesn't invent angles — Blender provides the spatial truth,
AI only applies materials/lighting/style.

Run headless (Blender does NOT need to be open):
  blender --background /Users/thaqif/Projects/limpahan/LE-v3.blend \
    --python pipeline/blender_viewport_export.py

With options:
  blender --background /path/to/file.blend \
    --python pipeline/blender_viewport_export.py -- \
    --output pipeline/refs \
    --resolution 1920 1080 \
    --preset product

Camera presets:
  product   — 7 standard product photography angles (hero, front, rear, sides, top, detail)
  turntable — 12 angles at 30° increments around the model
  custom    — single angle at specified azimuth/elevation
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
    parser.add_argument("--resolution", "-r", nargs=2, type=int, default=[1920, 1080],
                       metavar=("W", "H"))
    parser.add_argument("--preset", "-p", default="product",
                       choices=["product", "turntable", "custom"])
    parser.add_argument("--azimuth", type=float, default=45, help="Custom: azimuth degrees")
    parser.add_argument("--elevation", type=float, default=25, help="Custom: elevation degrees")
    parser.add_argument("--focal-length", type=float, default=None,
                       help="Override focal length (mm). Auto-calculated if not set.")
    parser.add_argument("--transparent", action="store_true",
                       help="Transparent background (alpha channel)")
    return parser.parse_args(argv)


# Product photography camera definitions
# Each: (name, azimuth_deg, elevation_deg, focal_length_mm, distance_multiplier)
PRODUCT_SHOTS = [
    ("hero_3quarter",      45,   25,  85, 1.6),   # Classic 3/4 hero — the money shot
    ("front",               0,   15,  85, 1.6),   # Straight on, slight elevation
    ("rear_open",         180,   20,  85, 1.6),   # Rear view (doors side)
    ("side_left",         -90,   15, 100, 1.8),   # Left profile — longer lens, compressed
    ("side_right",         90,   15, 100, 1.8),   # Right profile
    ("top_3quarter",       45,   55,  65, 1.4),   # High angle overview
    ("detail_low",         30,    5, 135, 2.2),   # Low angle detail — telephoto compression
]

TURNTABLE_SHOTS = [
    (f"turn_{i:03d}deg", angle, 25, 85, 1.6)
    for i, angle in enumerate(range(0, 360, 30))
]


def get_scene_bounds():
    """Calculate bounding box of all visible mesh objects."""
    min_coord = Vector((float("inf"),) * 3)
    max_coord = Vector((float("-inf"),) * 3)

    count = 0
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.visible_get():
            for corner in obj.bound_box:
                world_corner = obj.matrix_world @ Vector(corner)
                min_coord.x = min(min_coord.x, world_corner.x)
                min_coord.y = min(min_coord.y, world_corner.y)
                min_coord.z = min(min_coord.z, world_corner.z)
                max_coord.x = max(max_coord.x, world_corner.x)
                max_coord.y = max(max_coord.y, world_corner.y)
                max_coord.z = max(max_coord.z, world_corner.z)
            count += 1

    if count == 0:
        return Vector((0, 0, 0)), 10.0

    center = (min_coord + max_coord) / 2
    diagonal = (max_coord - min_coord).length
    dimensions = max_coord - min_coord
    print(f"  Scene: {count} objects, dimensions {dimensions.x:.1f} x {dimensions.y:.1f} x {dimensions.z:.1f}")
    print(f"  Center: ({center.x:.1f}, {center.y:.1f}, {center.z:.1f}), diagonal: {diagonal:.1f}")
    return center, diagonal


def setup_camera(center, diagonal, azimuth_deg, elevation_deg, focal_mm, distance_mult,
                 focal_override=None):
    """Position camera with proper focal length and framing."""
    cam = bpy.data.objects.get("ProductCam")
    if not cam:
        cam_data = bpy.data.cameras.new("ProductCam")
        cam = bpy.data.objects.new("ProductCam", cam_data)
        bpy.context.scene.collection.objects.link(cam)

    bpy.context.scene.camera = cam

    focal = focal_override if focal_override else focal_mm
    distance = diagonal * distance_mult

    # Adjust distance for focal length to maintain similar framing
    # Longer focal = further back, tighter compression
    distance *= (focal / 85.0)

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)

    cam.location = Vector((
        center.x + distance * math.cos(el) * math.cos(az),
        center.y + distance * math.cos(el) * math.sin(az),
        center.z + distance * math.sin(el),
    ))

    # Point at center
    direction = center - cam.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()

    # Camera settings
    cam.data.lens = focal
    cam.data.clip_start = 0.1
    cam.data.clip_end = distance * 10
    cam.data.sensor_width = 36  # Full frame sensor

    return cam


def setup_render(args):
    """Configure fast EEVEE render settings."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.resolution[0]
    scene.render.resolution_y = args.resolution[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if args.transparent else "RGB"
    scene.render.film_transparent = args.transparent

    # EEVEE quality — fast but decent
    scene.eevee.taa_render_samples = 32


def export_shots(args, shots):
    """Render all camera angles."""
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    setup_render(args)
    center, diagonal = get_scene_bounds()

    print(f"\nRendering {len(shots)} camera angles...")
    print(f"  Resolution: {args.resolution[0]}x{args.resolution[1]}")
    print(f"  Output: {out}/\n")

    for name, az, el, focal, dist_mult in shots:
        setup_camera(center, diagonal, az, el, focal, dist_mult, args.focal_length)

        filepath = str(out / f"{name}.png")
        bpy.context.scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        print(f"  ✓ {name}.png  (az={az}° el={el}° f={args.focal_length or focal}mm)")

    # Cleanup
    cam = bpy.data.objects.get("ProductCam")
    if cam:
        bpy.data.objects.remove(cam, do_unlink=True)

    print(f"\nDone. {len(shots)} reference images → {out}/")
    print(f"\nNext step — apply consistent style with AI:")
    print(f"  STYLE_REF=path/to/your/best_kontext_result.jpg")
    print(f"  for f in {out}/*.png; do")
    print(f'    python pipeline/generate.py -p "photorealistic product render" \\')
    print(f"      -m photon --image-ref \"$f\" --image-weight 0.9 \\")
    print(f"      --style-ref \"$STYLE_REF\" --style-weight 0.8 \\")
    print(f"      -n 2 -o pipeline/output/styled/")
    print(f"  done")


def main():
    args = get_args()

    if args.preset == "product":
        shots = PRODUCT_SHOTS
    elif args.preset == "turntable":
        shots = TURNTABLE_SHOTS
    elif args.preset == "custom":
        shots = [("custom", args.azimuth, args.elevation, 85, 1.6)]

    export_shots(args, shots)


if __name__ == "__main__":
    main()
