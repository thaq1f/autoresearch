"""
Autoresearch-style iteration loop for image generation via fal.ai.

The autoresearch methodology applied to creative work:
  prompt → generate → evaluate → keep/discard → refine → repeat

Start cheap (flux-schnell at $0.003), upgrade models as you converge on a look.

Usage:
  python pipeline/iterate.py \
    --prompt "hydrogen fuel cell container, dark cinematic, volumetric lighting" \
    --image-ref pipeline/refs/view_00.png \
    --rounds 3 --variations 4

  # Start cheap, upgrade as you go
  python pipeline/iterate.py \
    --prompt "solar panel deployment" \
    --model flux-schnell \
    --rounds 5 --variations 4

Each round:
  1. Generates N variations
  2. Opens them in Preview for comparison
  3. You pick the best (1-N) or reject all
  4. Winner becomes the image reference for next round
  5. You can refine the prompt and switch models between rounds
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Iterative image generation loop")
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--model", "-m", default="flux-schnell",
                       help="Starting model (can upgrade between rounds)")
    parser.add_argument("--aspect-ratio", "-a", default="16:9")
    parser.add_argument("--image-ref", "-i", action="append")
    parser.add_argument("--variations", "-n", type=int, default=4)
    parser.add_argument("--rounds", "-r", type=int, default=3)
    parser.add_argument("--output", "-o", default="pipeline/iterations")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from generate import generate, ensure_fal, MODELS
    ensure_fal()

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = Path(args.output) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    current_prompt = args.prompt
    current_image_refs = args.image_ref or []
    model = args.model
    log = []
    total_cost = 0.0

    print(f"\n{'='*60}")
    print(f"  IMAGE ITERATION (autoresearch loop)")
    print(f"  Session: {session_id}")
    print(f"  {args.rounds} rounds x {args.variations} variations")
    print(f"  Starting model: {model} (~${MODELS[model]['cost']}/img)")
    print(f"{'='*60}\n")

    for round_num in range(1, args.rounds + 1):
        round_dir = session_dir / f"round_{round_num:02d}"

        print(f"\n{'─'*40}")
        print(f"  Round {round_num}/{args.rounds} | Model: {model}")
        print(f"  Prompt: {current_prompt[:60]}...")
        print(f"{'─'*40}")

        results = generate(
            prompt=current_prompt,
            model_key=model,
            aspect_ratio=args.aspect_ratio,
            image_refs=current_image_refs if current_image_refs else None,
            variations=args.variations,
            output_dir=str(round_dir),
        )

        round_cost = len(results) * MODELS[model]["cost"]
        total_cost += round_cost

        if not results:
            print("No results. Stopping.")
            break

        # Open in Preview
        subprocess.run(["open"] + [str(r) for r in results])

        print(f"\nPick the best (cost so far: ${total_cost:.3f}):")
        for idx, r in enumerate(results, 1):
            print(f"  {idx}. {r.name}")
        print(f"  0. Reject all")
        print(f"  q. Done, stop iterating")

        choice = input(f"\nChoice [1-{len(results)}/0/q]: ").strip()

        if choice.lower() == "q":
            break
        elif choice == "0":
            log.append({"round": round_num, "status": "rejected", "model": model})
            continue

        try:
            winner = results[int(choice) - 1]
        except (ValueError, IndexError):
            winner = results[0]

        print(f"Kept: {winner.name}")
        log.append({
            "round": round_num,
            "status": "kept",
            "winner": str(winner),
            "model": model,
            "prompt": current_prompt,
        })

        # Winner becomes reference for next round
        current_image_refs = [str(winner)]

        if round_num < args.rounds:
            # Prompt refinement
            new_prompt = input(f"\nRefine prompt (Enter to keep): ").strip()
            if new_prompt:
                current_prompt = new_prompt

            # Model switching
            print(f"\nCurrent: {model} (${MODELS[model]['cost']})")
            print(f"Switch? Enter model name or press Enter to keep:")
            sorted_models = sorted(MODELS.items(), key=lambda x: x[1]["cost"])
            for key, m in sorted_models:
                marker = " ←" if key == model else ""
                ref_tag = " [img-ref]" if m["supports_image_ref"] else ""
                print(f"  {key:<20} ${m['cost']:<8}{ref_tag}{marker}")

            new_model = input(f"\nModel: ").strip()
            if new_model and new_model in MODELS:
                model = new_model
                print(f"Switched to {model}")

    # Save session log
    log_data = {
        "session_id": session_id,
        "initial_prompt": args.prompt,
        "total_cost": total_cost,
        "rounds": log,
    }
    log_path = session_dir / "session.json"
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  Session complete")
    print(f"  Total cost: ${total_cost:.3f}")
    print(f"  Saved to: {session_dir}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
