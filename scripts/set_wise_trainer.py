"""Set-wise QLoRA trainer with overfitting prevention + auto-resume.
Progressive set-wise training (each set builds on previous).
Auto-detects last completed set and resumes from there.
Usage:
  python scripts/set_wise_trainer.py --config config/finetune.yaml --data-dir data/massive --base-model Qwen/Qwen2.5-3B-Instruct
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Completely eliminate PyTorch CUDA memory fragmentation on 8GB cards
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

from pathlib import Path

import torch
import yaml
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    TrainerCallback,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
    EarlyStoppingCallback,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
from datasets import load_dataset


class CleanCacheCallback(TrainerCallback):
    """Flushes CUDA cache after evals and every 50 steps to prevent OOM."""
    def on_evaluate(self, args, state, control, **kwargs):
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step % 50 == 0 and torch.cuda.is_available():
            torch.cuda.empty_cache()


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tokenize_fn(example, tokenizer, max_seq_length):
    ids = tokenizer(
        example["text"],
        truncation=True,
        max_length=max_seq_length,
        padding="max_length",
    )
    ids["labels"] = ids["input_ids"].copy()
    return ids


def load_base_model(base_model: str, cfg: dict | None = None):
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = torch.bfloat16 if (cfg and cfg.get("bnb", {}).get("bnb_4bit_compute_dtype") == "bfloat16") else torch.float16
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb,
        device_map={"": 0},  # Force GPU 0
        trust_remote_code=True,
        attn_implementation="sdpa",
        token=os.environ.get("HF_TOKEN"),
    )
    model = prepare_model_for_kbit_training(model)
    return model, tokenizer


def apply_lora(model, cfg):
    qlora = cfg["qlora"]
    lora = LoraConfig(
        r=qlora["r"],
        lora_alpha=qlora["lora_alpha"],
        lora_dropout=qlora["lora_dropout"],
        target_modules=qlora["target_modules"],
        bias=qlora["bias"],
        task_type=qlora["task_type"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    return model


def find_last_completed_set(output_dir: Path) -> int:
    """Scan output_dir for completed set_XXX dirs with adapter_model.safetensors."""
    if not output_dir.exists():
        return -1
    last = -1
    for child in output_dir.iterdir():
        if child.is_dir() and child.name.startswith("set_"):
            try:
                idx = int(child.name.split("_")[1])
            except ValueError:
                continue
            if (child / "adapter_model.safetensors").exists():
                last = max(last, idx)
    return last


def train_set(model, tokenizer, train_path, val_path, output_dir, train_cfg, set_idx: int):
    # Ensure all paths are strings (WindowsPath objects break HF datasets)
    train_path = str(train_path)
    val_path = str(val_path)
    output_dir = str(output_dir)

    train_ds = load_dataset("json", data_files=train_path, split="train")
    val_ds = load_dataset("json", data_files=val_path, split="train")

    ms = train_cfg["max_seq_length"]
    train_ds = train_ds.map(
        lambda e: tokenize_fn(e, tokenizer, ms), batched=True, remove_columns=train_ds.column_names
    )
    val_ds = val_ds.map(
        lambda e: tokenize_fn(e, tokenizer, ms), batched=True, remove_columns=val_ds.column_names
    )

    weight_decay = float(train_cfg.get("weight_decay", 0.01))
    max_grad_norm = float(train_cfg.get("max_grad_norm", 1.0))
    early_stop_patience = int(train_cfg.get("early_stop_patience", 3))

    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=train_cfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=float(train_cfg["learning_rate"]),
        weight_decay=weight_decay,
        max_grad_norm=max_grad_norm,
        num_train_epochs=train_cfg["num_train_epochs"],
        lr_scheduler_type=train_cfg["lr_scheduler_type"],
        warmup_steps=train_cfg["warmup_steps"],
        logging_steps=train_cfg["logging_steps"],
        save_steps=train_cfg["save_steps"],
        save_total_limit=1,
        fp16=train_cfg["fp16"],
        bf16=train_cfg.get("bf16", False),
        gradient_checkpointing=train_cfg["gradient_checkpointing"],
        optim=train_cfg["optim"],
        tf32=True,
        dataloader_num_workers=train_cfg.get("dataloader_num_workers", 0),
        dataloader_pin_memory=True,
        report_to="none",
        save_strategy="steps",
        eval_strategy="steps",
        eval_steps=train_cfg["save_steps"],
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
    )

    early_stop = EarlyStoppingCallback(
        early_stopping_patience=early_stop_patience,
        early_stopping_threshold=0.0,
    )

    model.train()
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        callbacks=[early_stop, CleanCacheCallback()],
    )

    print(f"[train] Set {set_idx}: training on {train_path} -> {output_dir}")
    train_result = trainer.train()
    eval_metrics = trainer.evaluate()

    train_loss = train_result.training_loss
    eval_loss = eval_metrics.get("eval_loss", float("nan"))
    epochs = train_result.metrics.get("epoch", train_cfg["num_train_epochs"])

    print(f"[train] Set {set_idx} complete | train_loss={train_loss:.4f} | eval_loss={eval_loss:.4f} | epochs={epochs:.2f}")

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    return {
        "set": set_idx,
        "train_loss": float(train_loss),
        "eval_loss": float(eval_loss),
        "epochs": float(epochs),
    }


class TeeLogger:
    def __init__(self, filename="training_log_v3.txt", stream=None):
        self.file = open(filename, "a", encoding="utf-8", buffering=1)
        self.stream = stream or sys.__stdout__

    def write(self, data):
        try:
            self.stream.write(data)
            self.stream.flush()
        except Exception:
            pass
        try:
            self.file.write(data)
            self.file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass
        try:
            self.file.flush()
        except Exception:
            pass


def main():
    # Enable full TF32 acceleration on NVIDIA Tensor Cores (Blackwell / RTX 5060)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    # Prevent Windows Modern Standby / Sleep from dropping CUDA context during training
    if sys.platform == "win32":
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED | ES_AWAYMODE_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002 | 0x00000040)
            print("[power] Windows sleep lock enabled (system will stay awake during training)")
        except Exception:
            pass

    # Setup TeeLogger to simultaneously write to stdout and training_log_v3.txt for web UI telemetry
    sys.stdout = TeeLogger("training_log_v3.txt", sys.stdout)
    sys.stderr = TeeLogger("training_log_v3.txt", sys.stderr)

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--data-dir", required=True, help="Dir with set_*.jsonl + manifest.json")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--start-set", type=int, default=None, help="Force start from this set index")
    args = parser.parse_args()

    cfg = load_config(args.config)
    train_cfg = cfg["training"]
    data_dir = Path(args.data_dir)

    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"[error] manifest.json not found in {data_dir}")
        sys.exit(1)

    with manifest_path.open() as f:
        manifest = json.load(f)

    num_sets = manifest["num_sets"]
    output_root = Path(train_cfg["output_dir"])

    # Auto-detect resume point if not specified
    start_set = args.start_set
    if start_set is None:
        start_set = find_last_completed_set(output_root) + 1
        print(f"[train] Auto-resume detected: starting from set {start_set}")

    if start_set >= num_sets:
        print(f"[train] All {num_sets} sets already completed!")
        return

    print(f"[train] Found {num_sets} sets. Starting from set {start_set}.")
    print(f"[train] Overfitting safeguards: weight_decay={train_cfg.get('weight_decay',0.01)}, "
          f"max_grad_norm={train_cfg.get('max_grad_norm',1.0)}, "
          f"early_stop_patience={train_cfg.get('early_stop_patience',3)}")

    # Load base model once
    model, tokenizer = load_base_model(args.base_model, cfg)

    # If resuming, load the previous set's adapter as the starting point
    if start_set > 0:
        prev_adapter = output_root / f"set_{start_set - 1:03d}"
        if prev_adapter.exists() and (prev_adapter / "adapter_model.safetensors").exists():
            print(f"[train] Loading previous adapter: {prev_adapter}")
            model = PeftModel.from_pretrained(model, str(prev_adapter), is_trainable=True)
        else:
            print(f"[train] Warning: previous adapter not found at {prev_adapter}, starting fresh LoRA")
            model = apply_lora(model, cfg)
    else:
        model = apply_lora(model, cfg)

    # Explicitly ensure all LoRA parameters have gradients enabled
    for name, param in model.named_parameters():
        if "lora" in name.lower():
            param.requires_grad = True
    model.print_trainable_parameters()

    all_metrics = []
    best_eval_loss_ever = float("inf")
    best_set = -1

    for set_idx in range(start_set, num_sets):
        set_path = data_dir / f"set_{set_idx:03d}.jsonl"
        if not set_path.exists():
            print(f"[train] Skipping missing {set_path}")
            continue

        # Cumulative cross-validation: fast stratified sample across prior sets + personal pairs
        val_sets = [data_dir / f"set_{i:03d}.jsonl" for i in range(set_idx)]
        val_path = None
        if val_sets:
            val_path = data_dir / f"val_cumulative_set_{set_idx:03d}.jsonl"
            sampled_lines = []
            # Always validate on personal conversations to monitor identity retention
            personal_file = Path("data/personal_conversations_train.jsonl")
            if personal_file.exists():
                sampled_lines.extend(personal_file.read_text(encoding="utf-8").splitlines())
            for vs in val_sets:
                if vs.exists():
                    vs_lines = vs.read_text(encoding="utf-8").splitlines()
                    step = max(1, len(vs_lines) // 8)
                    sampled_lines.extend(vs_lines[::step][:8])
            # Cap at 180 to guarantee evaluation finishes in ~10s with zero VRAM pressure
            if len(sampled_lines) > 180:
                sampled_lines = sampled_lines[:180]
            with val_path.open("w", encoding="utf-8") as out:
                out.write("\n".join(sampled_lines) + "\n")
            print(f"[train] Created fast stratified val: {val_path} ({len(sampled_lines)} samples across {len(val_sets)} sets)")

        if val_path is None:
            default_val = Path("data/hinglish_val.jsonl")
            val_path = str(default_val) if default_val.exists() else str(set_path)

        set_output = output_root / f"set_{set_idx:03d}"
        set_output.mkdir(parents=True, exist_ok=True)

        metrics = train_set(model, tokenizer, str(set_path), val_path, set_output, train_cfg, set_idx)
        all_metrics.append(metrics)

        if metrics["eval_loss"] < best_eval_loss_ever:
            best_eval_loss_ever = metrics["eval_loss"]
            best_set = set_idx

        print(f"[train] Best so far: set {best_set} | eval_loss={best_eval_loss_ever:.4f}")

    # Summary
    summary_path = output_root / "training_summary.json"
    summary = {
        "total_sets": num_sets,
        "completed_sets": len(all_metrics) + start_set,
        "started_from_set": start_set,
        "best_set": best_set,
        "best_eval_loss": best_eval_loss_ever,
        "per_set": all_metrics,
        "status": "complete" if len(all_metrics) + start_set >= num_sets else "incomplete",
    }
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[train] Sets {start_set}-{num_sets-1} complete.")
    print(f"[train] Best set: {best_set} | Best eval_loss: {best_eval_loss_ever:.4f}")
    print(f"[train] Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
