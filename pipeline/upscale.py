"""
Phase 2: Upscale the locked reference style frame to 4K.

Usage:
  # Quick deterministic upscale (cheapest)
  python pipeline/upscale.py pipeline/output/light_test/winner.jpg

  # Magnific-style creative upscale (adds detail via AI)
  python pipeline/upscale.py pipeline/output/light_test/winner.jpg -m clarity

  # Professional grade
  python pipeline/upscale.py pipeline/output/light_test/winner.jpg -m topaz

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


UPSCALERS = {
    "esrgan": {
        "endpoint": "fal-ai/esrgan",
        "cost": 0.005,
        "description": "Fast deterministic 4x upscale — no hallucination, cheapest",
    },
    "clarity": {
        "endpoint": "fal-ai/clarity-upscaler",
        "cost": 0.04,
        "description": "Magnific-style creative upscale — adds AI detail",
    },
    "topaz": {
        "endpoint": "fal-ai/topaz/upscale/image",
        "cost": 0.08,
        "description": "Professional grade — multiple specialized models",
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


def upscale(image_path: str, model: str = "clarity", scale: int = 2,
            prompt: str = "", creativity: float = 0.35, output_dir: str = None):
    import fal_client
    import requests

    if not os.environ.get("FAL_KEY"):
        print("Error: set FAL_KEY environment variable")
        sys.exit(1)

    if model not in UPSCALERS:
        print(f"Unknown upscaler: {model}")
        print(f"Available: {', '.join(UPSCALERS.keys())}")
        sys.exit(1)

    upscaler = UPSCALERS[model]
    image_url = upload_if_local(image_path)

    # Build args per model
    if model == "esrgan":
        arguments = {
            "image_url": image_url,
            "scale": scale,
        }
    elif model == "clarity":
        arguments = {
            "image_url": image_url,
            "upscale_factor": scale,
            "creativity": creativity,
            "resemblance": max(0.0, 1.0 - creativity),
        }
        if prompt:
            arguments["prompt"] = prompt
    elif model == "topaz":
        arguments = {
            "image_url": image_url,
            "upscale_factor": scale,
            "model": "Standard V2",
        }

    print(f"\nUpscaling with {model} ({upscaler['description']})")
    print(f"  Scale: {scale}x")
    if model == "clarity":
        print(f"  Creativity: {creativity}")

    result = fal_client.run(upscaler["endpoint"], arguments=arguments)

    # Extract image URL
    image_result_url = None
    if "image" in result:
        image_result_url = result["image"]["url"] if isinstance(result["image"], dict) else result["image"]
    elif "images" in result and result["images"]:
        image_result_url = result["images"][0]["url"]

    if not image_result_url:
        print(f"FAILED: {json.dumps(result, indent=2)[:300]}")
        sys.exit(1)

    # Download
    resp = requests.get(image_result_url, stream=True)
    src = Path(image_path)
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = src.parent

    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{src.stem}_upscaled_{model}_{scale}x_{timestamp}.jpg"

    with open(out_path, "wb") as f:
        f.write(resp.content)

    print(f"  Saved: {out_path}")
    print(f"  Cost: ~${upscaler['cost']}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Upscale images via fal.ai")
    parser.add_argument("image", help="Image to upscale (local path or URL)")
    parser.add_argument("--model", "-m", default="clarity",
                       choices=list(UPSCALERS.keys()),
                       help="Upscaler model (default: clarity)")
    parser.add_argument("--scale", "-s", type=int, default=2,
                       help="Upscale factor (default: 2)")
    parser.add_argument("--prompt", "-p", default="",
                       help="Guide the upscaler (clarity only)")
    parser.add_argument("--creativity", "-c", type=float, default=0.35,
                       help="AI detail hallucination 0-1 (clarity only, default: 0.35)")
    parser.add_argument("--output", "-o", default=None,
                       help="Output directory")
    parser.add_argument("--list", "-l", action="store_true",
                       help="List available upscalers")
    args = parser.parse_args()

    if args.list:
        print("\nAvailable upscalers:\n")
        for key, u in UPSCALERS.items():
            print(f"  {key:<12} ~${u['cost']:<8} {u['description']}")
        print()
        return

    ensure_fal()
    upscale(args.image, model=args.model, scale=args.scale,
            prompt=args.prompt, creativity=args.creativity,
            output_dir=args.output)


if __name__ == "__main__":
    main()
