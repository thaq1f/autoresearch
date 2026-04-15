"""
Phase 3: Transfer the locked look onto your 3D animation via video-to-video.

The Brandon Lerry workflow:
  - Input 1: Your upscaled "Reference Style Frame" (the perfect look)
  - Input 2: Your untextured 3D animation (from Blender)
  - Output: Photorealistic video with the style frame's look applied to the motion

Usage:
  # Kling O1 video-to-video (best for style transfer)
  python pipeline/transfer.py \
    --style pipeline/output/winner_upscaled_4k.jpg \
    --video /Users/thaqif/Projects/limpahan/render_output/animation.mp4 \
    --prompt "Apply the photorealistic materials and lighting from the reference image"

  # Luma Ray2 image-to-video (animate a still frame)
  python pipeline/transfer.py \
    --style pipeline/output/winner_upscaled_4k.jpg \
    --prompt "slow orbit around the container" \
    -m luma-ray2

Environment:
  FAL_KEY=your_key_here
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


VIDEO_MODELS = {
    "kling-v2v": {
        "endpoint": "fal-ai/kling-video/o1/video-to-video/edit",
        "cost_per_sec": 0.168,
        "description": "Kling O1 video-to-video — style frame + source video → styled video",
        "mode": "video-to-video",
    },
    "luma-ray2": {
        "endpoint": "fal-ai/luma-dream-machine/ray-2/image-to-video",
        "cost_per_task": 0.50,
        "description": "Luma Ray2 — animate a still image into video",
        "mode": "image-to-video",
    },
    "kling-i2v": {
        "endpoint": "fal-ai/kling-video/v2.1/standard/image-to-video",
        "cost_per_sec": 0.084,
        "description": "Kling v2.1 image-to-video — animate from a single frame",
        "mode": "image-to-video",
    },
}


def ensure_fal():
    try:
        import fal_client
    except ImportError:
        print("Installing fal-client SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fal-client", "-q"])


def upload_if_local(path: str) -> str:
    if path.startswith("http"):
        return path
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}")
        sys.exit(1)
    import fal_client
    print(f"Uploading {p.name}...")
    url = fal_client.upload_file(str(p))
    return url


def transfer(style_path: str, video_path: str = None, prompt: str = "",
             model: str = "kling-v2v", duration: int = 5, output_dir: str = "pipeline/output/video"):
    import fal_client
    import requests

    if not os.environ.get("FAL_KEY"):
        print("Error: set FAL_KEY environment variable")
        sys.exit(1)

    if model not in VIDEO_MODELS:
        print(f"Unknown model: {model}")
        print(f"Available: {', '.join(VIDEO_MODELS.keys())}")
        sys.exit(1)

    vmodel = VIDEO_MODELS[model]
    style_url = upload_if_local(style_path)

    print(f"\n{'='*50}")
    print(f"  LOOK-TO-MOTION TRANSFER")
    print(f"  Model: {model} ({vmodel['description']})")
    print(f"  Style: {style_path}")
    if video_path:
        print(f"  Video: {video_path}")
    print(f"{'='*50}\n")

    if vmodel["mode"] == "video-to-video":
        if not video_path:
            print("Error: --video is required for video-to-video models")
            sys.exit(1)
        video_url = upload_if_local(video_path)

        # Kling O1 video-to-video edit
        arguments = {
            "video_url": video_url,
            "prompt": f"Transform this 3D animation to match the photorealistic style of @Image1. {prompt}",
            "image_urls": [style_url],
        }

    elif vmodel["mode"] == "image-to-video":
        # Image-to-video (Luma Ray2 or Kling i2v)
        if "luma" in model:
            arguments = {
                "prompt": prompt or "slow camera orbit, cinematic lighting",
                "image_url": style_url,
                "duration": "5s",
                "resolution": "540p",
                "aspect_ratio": "16:9",
            }
        else:
            # Kling i2v
            arguments = {
                "prompt": prompt or "slow camera orbit, cinematic lighting",
                "image_url": style_url,
                "duration": str(duration),
                "aspect_ratio": "16:9",
            }

    print("Generating video (this may take 1-5 minutes)...")

    # Use subscribe for long-running tasks
    result = fal_client.subscribe(vmodel["endpoint"], arguments=arguments,
                                   with_logs=True)

    # Extract video URL
    video_result_url = None
    if "video" in result:
        video_result_url = result["video"]["url"] if isinstance(result["video"], dict) else result["video"]
    elif "video_url" in result:
        video_result_url = result["video_url"]

    if not video_result_url:
        print(f"FAILED: {json.dumps(result, indent=2)[:500]}")
        sys.exit(1)

    # Download
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{timestamp}_{model}.mp4"

    resp = requests.get(video_result_url, stream=True)
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    # Save metadata
    meta = {
        "model": model,
        "style_ref": style_path,
        "video_source": video_path,
        "prompt": prompt,
        "timestamp": timestamp,
    }
    with open(out_path.with_suffix(".json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Saved: {out_path}")
    if "cost_per_sec" in vmodel:
        est_cost = vmodel["cost_per_sec"] * duration
        print(f"  Est cost: ~${est_cost:.2f}")
    else:
        print(f"  Est cost: ~${vmodel.get('cost_per_task', '?')}")

    # Open in QuickTime
    subprocess.run(["open", str(out_path)])
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Transfer look to motion via fal.ai video models")
    parser.add_argument("--style", "-s", required=True,
                       help="Style reference frame (your upscaled winner)")
    parser.add_argument("--video", "-v", default=None,
                       help="Source 3D animation video (for video-to-video)")
    parser.add_argument("--prompt", "-p", default="",
                       help="Additional prompt guidance")
    parser.add_argument("--model", "-m", default="kling-v2v",
                       choices=list(VIDEO_MODELS.keys()))
    parser.add_argument("--duration", "-d", type=int, default=5,
                       help="Duration in seconds (default: 5)")
    parser.add_argument("--output", "-o", default="pipeline/output/video")
    parser.add_argument("--list", "-l", action="store_true")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable video models:\n")
        for key, m in VIDEO_MODELS.items():
            cost = f"${m.get('cost_per_sec', m.get('cost_per_task', '?'))}"
            unit = "/sec" if "cost_per_sec" in m else "/task"
            print(f"  {key:<16} {cost}{unit:<12} {m['description']}")
        print()
        return

    ensure_fal()
    transfer(
        style_path=args.style,
        video_path=args.video,
        prompt=args.prompt,
        model=args.model,
        duration=args.duration,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
