"""Merge LoRA adapters with base Qwen2.5-3B model for standalone / Ollama use.

Run:
  python scripts/merge_lora.py --base Qwen/Qwen2.5-3B-Instruct --adapters models/lumi-qwen3-4b-hinglish --output models/lumi-qwen3-4b-hinglish-merged
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base model id (e.g. Qwen/Qwen2.5-3B-Instruct)")
    parser.add_argument("--adapters", required=True, help="Path to LoRA adapter dir")
    parser.add_argument("--output", required=True, help="Output dir for merged model")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", help="Device to merge on (cuda or cpu)")
    parser.add_argument("--push-hub", action="store_true", help="Push merged model to HF Hub")
    args = parser.parse_args()

    print(f"[merge] Base: {args.base}")
    print(f"[merge] Adapters: {args.adapters}")
    print(f"[merge] Output: {args.output}")
    print(f"[merge] Device: {args.device}")

    # ---- tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ---- base model (load in fp16 for merge, no quantization)
    base_model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        device_map=args.device,
        trust_remote_code=True,
    )

    # ---- apply LoRA
    model = PeftModel.from_pretrained(base_model, args.adapters)
    model = model.merge_and_unload()  # folds LoRA weights into base

    # ---- save merged
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    print(f"[merge] Saved merged model to {out}")

    if args.push_hub:
        model.push_to_hub(args.push_hub)
        tokenizer.push_to_hub(args.push_hub)
        print(f"[merge] Pushed to {args.push_hub}")


if __name__ == "__main__":
    main()
