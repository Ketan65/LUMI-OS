"""Quick sanity test: fine-tuned LUMI vs base model on Hinglish prompts."""

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import torch

BASE = "Qwen/Qwen2.5-3B-Instruct"
ADAPTERS = "models/lumi-qwen3-4b-hinglish"

print("Loading base model (4-bit)…")
tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)
base = AutoModelForCausalLM.from_pretrained(
    BASE, quantization_config=bnb, device_map="auto", trust_remote_code=True
)

print("Loading fine-tuned adapters…")
ft = PeftModel.from_pretrained(base, ADAPTERS)

PROMPTS = [
    "tum kon ho?",
    "kya tum Hindi bol sakte ho?",
    "kya tum offline kaam karte ho?",
    "chai banana sikhao",
    "main bahut tanaav mein hoon",
    "hey lumi, sun raho ho?",
]

for p in PROMPTS:
    text = f"User: {p}\nAssistant:"
    inputs = tok(text, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = ft.generate(**inputs, max_new_tokens=60, temperature=0.7, do_sample=True)
    reply = tok.decode(out[0], skip_special_tokens=True)
    reply = reply.replace(text, "").strip()
    print(f"\nQ: {p}")
    print(f"A: {reply[:200]}")

print("\nFine-tuned model sanity test complete.")
