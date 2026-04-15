#!/bin/bash
set -e

# =============================================================
#  BRANDON LERRY 3-PHASE PIPELINE
#
#  Phase 1: LOCK THE LOOK — iterate on ONE solid render
#  Phase 2: UPSCALE — 4K the winner
#  Phase 3: TRANSFER — video-to-video (style frame + 3D anim)
#
#  This script prints the commands for each phase.
#  Run them sequentially with human validation between steps.
# =============================================================

REFS_DIR="pipeline/refs/solid"
BLEND_FILE="/Users/thaqif/Projects/limpahan/LE-v3.blend"
BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"

echo ""
echo "============================================="
echo "  3D → AI REALISM PIPELINE"
echo "  (Brandon Lerry workflow)"
echo "============================================="
echo ""
echo "PHASE 0: SOLID RENDERS (if not done already)"
echo "─────────────────────────────────────────────"
echo "  $BLENDER \\"
echo "    --background $BLEND_FILE \\"
echo "    --python pipeline/blender_product_angles.py -- \\"
echo "    --output pipeline/refs --passes solid"
echo ""

# Check for existing refs
REF_COUNT=$(ls "$REFS_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
if [ "$REF_COUNT" -eq 0 ]; then
    echo "  ⚠ No solid renders found. Run Phase 0 first."
    echo ""
    exit 0
fi

echo "  Found $REF_COUNT solid renders in $REFS_DIR/"
echo ""

# Pick the hero frame
HERO=$(ls "$REFS_DIR"/*.png | head -1)
echo "  Hero frame: $(basename $HERO)"
echo ""

echo "PHASE 1: LOCK THE LOOK (iterate on one frame)"
echo "─────────────────────────────────────────────"
echo "  Pick your hero frame, then iterate:"
echo ""
echo "  # Option A: flux-kontext (proven, \$0.04/img)"
echo "  python pipeline/iterate.py \\"
echo "    -p \"add photorealistic materials and studio lighting\" \\"
echo "    -m flux-kontext \\"
echo "    -i $HERO \\"
echo "    -r 3 -n 4"
echo ""
echo "  # Option B: flux-pro-redux (\$0.05/img)"
echo "  python pipeline/iterate.py \\"
echo "    -p \"photorealistic product render, premium studio lighting, distinct materials per component\" \\"
echo "    -m flux-pro-redux \\"
echo "    -i $HERO \\"
echo "    -r 3 -n 4"
echo ""
echo "  # Option C: nano-banana-2-edit (\$0.08/img)"
echo "  python pipeline/iterate.py \\"
echo "    -p \"make photorealistic with distinct colored materials per component, studio lighting\" \\"
echo "    -m nano-banana-2-edit \\"
echo "    -i $HERO \\"
echo "    -r 3 -n 4"
echo ""

echo "PHASE 2: UPSCALE THE WINNER TO 4K"
echo "─────────────────────────────────────────────"
echo "  python pipeline/upscale.py /path/to/your/winner.jpg -m clarity -s 4"
echo "  python pipeline/upscale.py /path/to/your/winner.jpg -m topaz -s 4"
echo ""

echo "PHASE 3: TRANSFER LOOK TO MOTION"
echo "─────────────────────────────────────────────"
echo "  # Video-to-video (need 3D animation exported as .mp4)"
echo "  python pipeline/transfer.py \\"
echo "    --style /path/to/winner_upscaled_4k.jpg \\"
echo "    --video /path/to/3d_animation.mp4 \\"
echo "    -p \"Apply the photorealistic look from the reference\""
echo ""
echo "  # Or animate the still frame directly"
echo "  python pipeline/transfer.py \\"
echo "    --style /path/to/winner_upscaled_4k.jpg \\"
echo "    -m luma-ray2 \\"
echo "    -p \"slow orbit around the container, cinematic\""
echo ""
echo "============================================="
echo "  Run each phase, validate, then proceed."
echo "============================================="
