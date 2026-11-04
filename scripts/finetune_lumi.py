"""QLoRA fine-tune script for LUMI (qwen3:4b, Hinglish, 8GB VRAM safe).

Prerequisites:
  pip install -r requirements-finetune.txt
  export HF_TOKEN="..."  # if Qwen3-4B-Instruct is gated

Run:
  python scripts/finetune_lumi.py --config config/finetune.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import load_dataset


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tokenize(example, tokenizer, max_seq_length: int):
    ids = tokenizer(
        example["text"],
        truncation=True,
        max_length=max_seq_length,
        padding="max_length",
    )
    ids["labels"] = ids["input_ids"].copy()
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to config/finetune.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg = cfg["model"]
    qlora_cfg = cfg["qlora"]
    bnb_cfg = cfg["bnb"]
    train_cfg = cfg["training"]
    data_cfg = cfg["data"]

    print(f"[ft] Base model: {model_cfg['base_model']}")
    print(f"[ft] Output dir: {train_cfg['output_dir']}")

    # Ensure numeric types (YAML can parse 2e-4 as string on some versions)
    train_cfg["learning_rate"] = float(train_cfg["learning_rate"])

    # ---- tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_cfg["base_model"], trust_remote_code=True, token=os.environ.get("HF_TOKEN")
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ---- 4-bit quantized base model
    bnb = BitsAndBytesConfig(
        load_in_4bit=bnb_cfg["load_in_4bit"],
        bnb_4bit_compute_dtype=getattr(torch, bnb_cfg["bnb_4bit_compute_dtype"]),
        bnb_4bit_quant_type=bnb_cfg["bnb_4bit_quant_type"],
        bnb_4bit_use_double_quant=bnb_cfg["bnb_4bit_use_double_quant"],
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_cfg["base_model"],
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
        token=os.environ.get("HF_TOKEN"),
    )
    model = prepare_model_for_kbit_training(model)

    # ---- LoRA
    lora = LoraConfig(
        r=qlora_cfg["r"],
        lora_alpha=qlora_cfg["lora_alpha"],
        lora_dropout=qlora_cfg["lora_dropout"],
        target_modules=qlora_cfg["target_modules"],
        bias=qlora_cfg["bias"],
        task_type=qlora_cfg["task_type"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    # ---- datasets
    train_ds = load_dataset("json", data_files=data_cfg["train_file"], split="train")
    val_ds = load_dataset("json", data_files=data_cfg["val_file"], split="train")

    train_ds = train_ds.map(
        lambda e: tokenize(e, tokenizer, train_cfg["max_seq_length"]),
        batched=True,
        remove_columns=train_ds.column_names,
    )
    val_ds = val_ds.map(
        lambda e: tokenize(e, tokenizer, train_cfg["max_seq_length"]),
        batched=True,
        remove_columns=val_ds.column_names,
    )

    # ---- trainer
    args = TrainingArguments(
        output_dir=train_cfg["output_dir"],
        per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=train_cfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
        learning_rate=train_cfg["learning_rate"],
        num_train_epochs=train_cfg["num_train_epochs"],
        lr_scheduler_type=train_cfg["lr_scheduler_type"],
        warmup_steps=train_cfg["warmup_steps"],
        logging_steps=train_cfg["logging_steps"],
        save_steps=train_cfg["save_steps"],
        save_total_limit=train_cfg["save_total_limit"],
        fp16=train_cfg["fp16"],
        gradient_checkpointing=train_cfg["gradient_checkpointing"],
        optim=train_cfg["optim"],
        report_to="none",
        save_strategy="steps",
        eval_strategy="steps",
        eval_steps=train_cfg["save_steps"],
        load_best_model_at_end=True,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    print("[ft] Starting training…")
    trainer.train()

    # ---- save
    Path(train_cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(train_cfg["output_dir"])
    tokenizer.save_pretrained(train_cfg["output_dir"])
    print(f"[ft] Saved to {train_cfg['output_dir']}")
    print("[ft] Next: convert to Ollama GGUF and `ollama create lumi-qwen3:4b -f Modelfile`")


if __name__ == "__main__":
    main()
