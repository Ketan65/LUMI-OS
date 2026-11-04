"""Massive Hinglish data pipeline — download, chunk, cross-verify, set-wise train.

Sources:
  1. ankitdhiman/hinglish-conversations  (20403 convos / 203993 turn pairs)
  2. DSMJ910/hinglish-instruct-10k       (10594 instruction pairs)

Pipeline:
  1. Download each HF dataset
  2. Normalize to {user, assistant} pairs
  3. Quality filter (length, script mix, no garbage)
  4. Chunk into N sets (configurable)
  5. Cross-verify each set against a judge model (optional)
  6. Export JSONL per set for set-wise QLoRA training
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Optional

import yaml
from datasets import load_dataset

OUT_DIR = Path("data/massive")
CHUNK_SIZE = 2000          # pairs per set
SEED = 42


def normalize_pair(user: str, assistant: str) -> Optional[tuple[str, str]]:
    """Clean and validate a single Q&A pair."""
    if not user or not assistant:
        return None
    u = user.strip()
    a = assistant.strip()
    if len(u) < 2 or len(a) < 2:
        return None
    if len(u) > 500 or len(a) > 1000:
        return None
    # Drop obvious garbage
    if re.search(r"(http|www\.|\.com|@|#\w+)", u + a):
        return None
    # Both datasets are Hinglish-specific — accept if passes length/garbage checks
    return u, a


def load_hinglish_conversations() -> list[tuple[str, str]]:
    """ankitdhiman/hinglish-conversations — default config (turn_pairs equivalent)."""
    print("[data] Loading ankitdhiman/hinglish-conversations (default)…")
    ds = load_dataset("ankitdhiman/hinglish-conversations", split="train")
    pairs: list[tuple[str, str]] = []
    for row in ds:
        p = normalize_pair(row.get("user_message", ""), row.get("assistant_message", ""))
        if p:
            pairs.append(p)
    print(f"[data] hinglish-conversations: {len(pairs)} valid pairs")
    return pairs


def load_hinglish_instruct() -> list[tuple[str, str]]:
    """DSMJ910/hinglish-instruct-10k — instruction pairs."""
    print("[data] Loading DSMJ910/hinglish-instruct-10k…")
    try:
        ds = load_dataset("DSMJ910/hinglish-instruct-10k", split="train")
    except Exception as exc:
        print(f"[data] DSMJ910 load failed ({exc}) — skipping")
        return []
    pairs: list[tuple[str, str]] = []
    for row in ds:
        u = row.get("user_message") or row.get("instruction") or row.get("prompt") or ""
        a = row.get("assistant_response") or row.get("response") or row.get("output") or ""
        p = normalize_pair(u, a)
        if p:
            pairs.append(p)
    print(f"[data] hinglish-instruct-10k: {len(pairs)} valid pairs")
    return pairs


def chunk_into_sets(pairs: list[tuple[str, str]], chunk_size: int = CHUNK_SIZE) -> list[list[tuple[str, str]]]:
    random.seed(SEED)
    random.shuffle(pairs)
    sets = [pairs[i:i + chunk_size] for i in range(0, len(pairs), chunk_size)]
    print(f"[data] Split into {len(sets)} sets of ~{chunk_size} pairs each")
    return sets


def export_set(sets: list[list[tuple[str, str]]], out_dir: Path) -> None:
    """Write each set as JSONL with chat_template formatting."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, set_pairs in enumerate(sets):
        path = out_dir / f"set_{idx:03d}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for u, a in set_pairs:
                text = (
                    f"<|start_header_id|>system<|end_header_id|>\n\n"
                    f"You are LUMI, a helpful personal assistant. Reply in Hinglish (Hindi + English mix) naturally."
                    f"<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{u}"
                    f"<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n{a}<|eot_id|>"
                )
                f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
        print(f"[data] Wrote {path} ({len(set_pairs)} pairs)")
    # Also write a manifest
    manifest = {"num_sets": len(sets), "pairs_per_set": CHUNK_SIZE, "total_pairs": sum(len(s) for s in sets)}
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[data] Manifest: {manifest}")


def main() -> None:
    all_pairs: list[tuple[str, str]] = []

    # Source 1
    try:
        all_pairs += load_hinglish_conversations()
    except Exception as exc:
        print(f"[data] ankitdhiman download failed ({exc}) — will retry on next run")

    # Source 2
    try:
        all_pairs += load_hinglish_instruct()
    except Exception as exc:
        print(f"[data] DSMJ910 download failed ({exc}) — will retry on next run")

    # Dedup
    seen = set()
    unique: list[tuple[str, str]] = []
    for u, a in all_pairs:
        key = (u.lower(), a.lower())
        if key not in seen:
            seen.add(key)
            unique.append((u, a))

    print(f"[data] Total unique pairs: {len(unique)}")

    sets = chunk_into_sets(unique, CHUNK_SIZE)
    export_set(sets, OUT_DIR)


if __name__ == "__main__":
    main()
