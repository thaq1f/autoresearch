"""
Universal image generation pipeline via fal.ai.

One API, many models — switch between them based on quality/speed/cost needs.

Usage:
  # Cheapest drafts ($0.003/image)
  python pipeline/generate.py -p "hydrogen fuel cell, cinematic" -m flux-schnell

  # Image-to-image editing (keep structure, change style)
  python pipeline/generate.py -p "make it look like a SpaceX render" -m flux-kontext \
    --image-ref pipeline/refs/solid/01_hero_3quarter.png

  # Flux Pro Redux (image-to-image, high quality)
  python pipeline/generate.py -p "photorealistic product render" -m flux-pro-redux \
    --image-ref pipeline/refs/solid/01_hero_3quarter.png

  # Nano Banana (Gemini image gen, great for creative edits)
  python pipeline/generate.py -p "product photography" -m nano-banana-2 \
    --image-ref pipeline/refs/solid/01_hero_3quarter.png

Environment:
  FAL_KEY=your_key_here
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# Model registry: fal.ai endpoint → metadata
MODELS = {
    "sana-sprint": {
        "endpoint": "fal-ai/sana-sprint",
        "cost": 0.0025,
        "supports_image_ref": False,
        "description": "Fastest, cheapest drafts",
    },
    "flux-schnell": {
        "endpoint": "fal-ai/flux/schnell",
        "cost": 0.003,
        "supports_image_ref": False,
        "description": "Fast iteration, good quality",
    },
    "sdxl": {
        "endpoint": "fal-ai/fast-sdxl",
        "cost": 0.003,
        "supports_image_ref": False,
        "description": "Stable Diffusion XL, LoRA ecosystem",
    },
    "photon-flash": {
        "endpoint": "fal-ai/luma-photon/flash",
        "cost": 0.005,
        "supports_image_ref": True,
        "description": "Photorealistic, fast",
    },
    "photon": {
        "endpoint": "fal-ai/luma-photon",
        "cost": 0.015,
        "supports_image_ref": True,
        "description": "Photorealistic, high quality",
    },
    "flux-dev": {
        "endpoint": "fal-ai/flux/dev",
        "cost": 0.025,
        "supports_image_ref": False,
        "description": "High quality open model",
    },
    "flux-dev-i2i": {
        "endpoint": "fal-ai/flux/dev/image-to-image",
        "cost": 0.03,
        "supports_image_ref": True,
        "description": "Image-to-image with Flux Dev",
    },
    "ideogram-turbo": {
        "endpoint": "fal-ai/ideogram/v3/turbo",
        "cost": 0.03,
        "supports_image_ref": False,
        "description": "Great text rendering in images",
    },
    "flux-pro": {
        "endpoint": "fal-ai/flux-pro/v1.1",
        "cost": 0.04,
        "supports_image_ref": False,
        "description": "Excellent quality",
    },
    "flux-kontext": {
        "endpoint": "fal-ai/flux-pro/kontext",
        "cost": 0.04,
        "supports_image_ref": True,
        "description": "Best for editing existing images",
    },
    "ideogram-quality": {
        "endpoint": "fal-ai/ideogram/v3/quality",
        "cost": 0.09,
        "supports_image_ref": False,
        "description": "Top tier quality",
    },
    "flux-pro-redux": {
        "endpoint": "fal-ai/flux-pro/v1.1/redux",
        "cost": 0.05,
        "supports_image_ref": True,
        "description": "Flux Pro image-to-image — restyle while preserving structure",
    },
    "nano-banana": {
        "endpoint": "fal-ai/nano-banana",
        "cost": 0.039,
        "supports_image_ref": False,
        "description": "Gemini image gen — text-to-image",
    },
    "nano-banana-2": {
        "endpoint": "fal-ai/nano-banana-2",
        "cost": 0.08,
        "supports_image_ref": True,
        "description": "Gemini 3.1 Flash — text + image editing, great quality",
    },
    "nano-banana-2-edit": {
        "endpoint": "fal-ai/nano-banana-2/edit",
        "cost": 0.08,
        "supports_image_ref": True,
        "description": "Gemini 3.1 Flash edit mode — best for restyling solid renders",
    },
    "nano-banana-pro": {
        "endpoint": "fal-ai/nano-banana-pro",
        "cost": 0.15,
        "supports_image_ref": True,
        "description": "Gemini 3 Pro — highest quality Gemini image gen",
    },
    "nano-banana-pro-edit": {
        "endpoint": "fal-ai/nano-banana-pro/edit",
        "cost": 0.15,
        "supports_image_ref": True,
        "description": "Gemini 3 Pro edit mode — premium restyling",
    },
    "flux-depth": {
        "endpoint": "fal-ai/flux-control-lora-depth",
        "cost": 0.04,
        "supports_image_ref": True,
        "description": "ControlNet depth — AI textures your 3D geometry",
    },
    "flux-canny": {
        "endpoint": "fal-ai/flux-control-lora-canny",
        "cost": 0.04,
        "supports_image_ref": True,
        "description": "ControlNet canny — AI textures from edge maps",
    },
    "flux-general": {
        "endpoint": "fal-ai/flux-general",
        "cost": 0.075,
        "supports_image_ref": True,
        "description": "ControlNet union — depth + canny combined",
    },
}


def ensure_fal():
    try:
        import fal_client
    except ImportError:
        print("Installing fal-client SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "fal-client", "-q"])


def upload_if_local(path: str) -> str:
    """Upload local file via fal.ai's built-in upload, or return URL as-is."""
    if path.startswith("http"):
        return path

    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}")
        sys.exit(1)

    import fal_client
    print(f"Uploading {p.name}...")
    url = fal_client.upload_file(str(p))
    print(f"  → {url}")
    return url


def build_arguments(model_key, prompt, aspect_ratio, image_refs, image_weight,
                    style_refs=None, style_weight=0.8):
    """Build model-specific arguments dict."""
    args = {"prompt": prompt}

    # Map aspect ratio to image size for models that use width/height
    sizes = {
        "16:9": (1024, 576),
        "9:16": (576, 1024),
        "1:1": (1024, 1024),
        "4:3": (1024, 768),
        "3:4": (768, 1024),
        "21:9": (1024, 440),
        "9:21": (440, 1024),
    }
    w, h = sizes.get(aspect_ratio, (1024, 576))

    model = MODELS[model_key]
    endpoint = model["endpoint"]

    if "nano-banana" in endpoint:
        # Gemini-based models
        if "/edit" in endpoint:
            args["image_url"] = image_refs[0] if image_refs else None
        args["image_size"] = "landscape_4_3"  # or portrait_3_4, square_1_1
        if aspect_ratio == "16:9":
            args["image_size"] = "landscape_16_9"
        elif aspect_ratio == "9:16":
            args["image_size"] = "portrait_9_16"
        elif aspect_ratio == "1:1":
            args["image_size"] = "square_1_1"
        elif aspect_ratio == "4:3":
            args["image_size"] = "landscape_4_3"
        elif aspect_ratio == "3:4":
            args["image_size"] = "portrait_3_4"
        return args
    elif "flux-pro" in endpoint and "redux" in endpoint:
        # Flux Pro Redux — image-to-image
        args["image_url"] = image_refs[0] if image_refs else None
        args["image_size"] = {"width": w, "height": h}
        args["num_inference_steps"] = 28
        args["guidance_scale"] = 3.5
        args["image_prompt_strength"] = image_weight
        return args
    elif "flux" in endpoint and "kontext" not in endpoint:
        args["image_size"] = {"width": w, "height": h}
        args["num_inference_steps"] = 4 if "schnell" in endpoint else 28
        if image_refs and "image-to-image" in endpoint:
            args["image_url"] = image_refs[0]
            args["strength"] = 1.0 - image_weight
    elif "kontext" in endpoint:
        args["image_url"] = image_refs[0] if image_refs else None
        args["image_size"] = {"width": w, "height": h}
    elif "flux-control-lora-depth" in endpoint:
        args["control_lora_image_url"] = image_refs[0] if image_refs else None
        args["control_lora_strength"] = image_weight
        args["image_size"] = {"width": w, "height": h}
        args["num_inference_steps"] = 28
    elif "flux-control-lora-canny" in endpoint:
        args["control_lora_image_url"] = image_refs[0] if image_refs else None
        args["control_lora_strength"] = image_weight
        args["image_size"] = {"width": w, "height": h}
        args["num_inference_steps"] = 28
    elif "flux-general" == endpoint.split("/")[-1]:
        args["image_size"] = {"width": w, "height": h}
        args["num_inference_steps"] = 28
        args["guidance_scale"] = 3.5
        if image_refs:
            controls = []
            controls.append({
                "control_image_url": image_refs[0],
                "control_mode": "depth",
            })
            if len(image_refs) > 1:
                controls.append({
                    "control_image_url": image_refs[1],
                    "control_mode": "canny",
                })
            args["controlnet_unions"] = [{
                "path": "https://huggingface.co/Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro/resolve/main/diffusion_pytorch_model.safetensors",
                "controls": controls,
            }]
    elif "luma-photon" in endpoint:
        args["image_size"] = {"width": w, "height": h}
        if image_refs:
            args["image_ref"] = [{"url": ref, "weight": image_weight} for ref in image_refs]
        if style_refs:
            args["style_ref"] = [{"url": ref, "weight": style_weight} for ref in style_refs]
    elif "ideogram" in endpoint:
        args["image_size"] = {"width": w, "height": h}
    elif "sdxl" in endpoint:
        args["image_size"] = {"width": w, "height": h}
    elif "sana" in endpoint:
        args["image_size"] = {"width": w, "height": h}

    return args


def generate(
    prompt: str,
    model_key: str = "flux-schnell",
    aspect_ratio: str = "16:9",
    image_refs: list[str] | None = None,
    image_weight: float = 0.85,
    style_refs: list[str] | None = None,
    style_weight: float = 0.8,
    variations: int = 1,
    output_dir: str = "pipeline/output",
) -> list[Path]:
    import fal_client
    import requests

    if not os.environ.get("FAL_KEY"):
        print("Error: set FAL_KEY environment variable")
        print("Get your key at: https://fal.ai/dashboard/keys")
        sys.exit(1)

    if model_key not in MODELS:
        print(f"Unknown model: {model_key}")
        print(f"Available: {', '.join(MODELS.keys())}")
        sys.exit(1)

    model = MODELS[model_key]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Upload local files
    uploaded_refs = None
    if image_refs:
        if not model["supports_image_ref"] and "i2i" not in model_key and "kontext" not in model_key:
            print(f"  Note: {model_key} doesn't support image references, ignoring --image-ref")
            print(f"  Use flux-kontext, flux-dev-i2i, or photon-flash for image references")
            uploaded_refs = None
        else:
            uploaded_refs = [upload_if_local(ref) for ref in image_refs]

    uploaded_style_refs = None
    if style_refs:
        uploaded_style_refs = [upload_if_local(ref) for ref in style_refs]

    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i in range(variations):
        tag = f"v{i+1}" if variations > 1 else ""
        print(f"\nGenerating{f' variation {i+1}/{variations}' if variations > 1 else ''}...")
        print(f"  Model: {model_key} ({model['description']})")
        print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        if uploaded_style_refs:
            print(f"  Style ref: applied")

        arguments = build_arguments(model_key, prompt, aspect_ratio, uploaded_refs, image_weight,
                                    uploaded_style_refs, style_weight)

        result = fal_client.run(model["endpoint"], arguments=arguments)

        # Extract image URL from response
        image_url = None
        if "images" in result and result["images"]:
            image_url = result["images"][0]["url"]
        elif "image" in result:
            image_url = result["image"]["url"] if isinstance(result["image"], dict) else result["image"]

        if not image_url:
            print(f"  FAILED: no image in response")
            print(f"  Response: {json.dumps(result, indent=2)[:200]}")
            continue

        # Download
        resp = requests.get(image_url, stream=True)
        filename = f"{timestamp}_{model_key}_{tag}.jpg" if tag else f"{timestamp}_{model_key}.jpg"
        filepath = out / filename
        with open(filepath, "wb") as f:
            f.write(resp.content)

        # Save metadata
        meta = {
            "prompt": prompt,
            "model": model_key,
            "endpoint": model["endpoint"],
            "cost": model["cost"],
            "aspect_ratio": aspect_ratio,
            "image_refs": image_refs,
            "image_weight": image_weight,
            "style_refs": style_refs,
            "style_weight": style_weight,
            "output": str(filepath),
            "timestamp": timestamp,
        }
        meta_path = filepath.with_suffix(".json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        print(f"  Saved: {filepath}")
        print(f"  Cost: ~${model['cost']}")
        results.append(filepath)

    total_cost = len(results) * model["cost"]
    print(f"\nDone. {len(results)} image(s) → {out}/")
    print(f"Total cost: ~${total_cost:.3f}")
    return results


def list_models():
    print("\nAvailable models (cheapest first):\n")
    print(f"  {'Model':<20} {'Cost':<12} {'Img Ref':<10} {'Description'}")
    print(f"  {'─'*20} {'─'*12} {'─'*10} {'─'*30}")
    for key, m in sorted(MODELS.items(), key=lambda x: x[1]["cost"]):
        ref = "yes" if m["supports_image_ref"] else "—"
        print(f"  {key:<20} ${m['cost']:<11} {ref:<10} {m['description']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate images via fal.ai (multi-model)")
    parser.add_argument("--prompt", "-p", help="Text prompt")
    parser.add_argument("--model", "-m", default="flux-schnell",
                       help="Model name (use --list to see all)")
    parser.add_argument("--list", "-l", action="store_true", help="List available models")
    parser.add_argument("--aspect-ratio", "-a", default="16:9",
                       choices=["1:1", "3:4", "4:3", "9:16", "16:9", "9:21", "21:9"])
    parser.add_argument("--image-ref", "-i", action="append",
                       help="Image reference (local path or URL)")
    parser.add_argument("--image-weight", type=float, default=0.85,
                       help="Image reference influence 0.0-1.0 (default: 0.85)")
    parser.add_argument("--style-ref", "-s", action="append",
                       help="Style reference image (local path or URL). Applies consistent look.")
    parser.add_argument("--style-weight", type=float, default=0.8,
                       help="Style reference influence 0.0-1.0 (default: 0.8)")
    parser.add_argument("--variations", "-n", type=int, default=1,
                       help="Number of variations to generate")
    parser.add_argument("--output", "-o", default="pipeline/output",
                       help="Output directory")
    args = parser.parse_args()

    if args.list:
        list_models()
        return

    if not args.prompt:
        parser.error("--prompt is required (or use --list)")

    ensure_fal()
    generate(
        prompt=args.prompt,
        model_key=args.model,
        aspect_ratio=args.aspect_ratio,
        image_refs=args.image_ref,
        image_weight=args.image_weight,
        style_refs=args.style_ref,
        style_weight=args.style_weight,
        variations=args.variations,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
