import json
from torch.utils.data import Dataset
from sentence_transformers import CrossEncoder
from torch.utils.data import DataLoader


import os
from pathlib import Path

import torch
import torch.nn as nn
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1] 

## v1
# PAIRWISE_PATH = PROJECT_ROOT / "data" / "feedback" / "pairwise.jsonl"
# POINTWISE_PATH = PROJECT_ROOT / "data" / "feedback" / "pointwise.jsonl"
 
PAIRWISE_PATH = PROJECT_ROOT / "data" / "feedback" / "pairwise_clicklike_v4.jsonl"
POINTWISE_PATH = PROJECT_ROOT / "data" / "feedback" / "pointwise_v4.jsonl"

MODEL_NAME = "BAAI/bge-reranker-base"
OUTPUT_DIR = PROJECT_ROOT / "models" / "reranker" / "bge-reranker-v4"

class PairwiseDataset(Dataset):
    def __init__(self, path):
        self.data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                self.data.append((
                    obj["query_text"],
                    obj["pos_text"],
                    obj["neg_text"]
                ))

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        q, pos, neg = self.data[idx]
        return q, pos, neg


dataset = PairwiseDataset(PAIRWISE_PATH)

def clip_text(s: str, max_chars: int = 1800) -> str:
    s = (s or "").strip()
    return s[:max_chars]


def collate_fn(batch):
    # batch: List[(q, pos, neg)]
    qs, poss, negs = [], [], []
    for q, pos, neg in batch:
        qs.append(clip_text(q, 400))
        poss.append(clip_text(pos, 1800))
        negs.append(clip_text(neg, 1800))
    return qs, poss, negs


model = CrossEncoder(
    MODEL_NAME,
    num_labels=1,
    max_length=512
)

print("cwd =", os.getcwd())
print("output_dir =", Path(OUTPUT_DIR).resolve())
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.model.to(device)
model.model.train()

train_loader = DataLoader(
    dataset,
    shuffle=True,
    batch_size=8,
    collate_fn=collate_fn
)

num_epochs = 2
grad_accum_steps = 4

total_steps = (len(train_loader) * num_epochs) // grad_accum_steps
warmup_steps = int(0.06 * total_steps)


optimizer = AdamW(model.model.parameters(), lr=2e-5)
optimizer.zero_grad()
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps = warmup_steps,
    num_training_steps=total_steps
)

global_step = 0
for epoch in range(num_epochs):
    epoch_loss = 0.0
    for qs, poss, negs in train_loader:
        # tokenize pos / neg
        pos_inputs = model.tokenizer(
            qs, poss,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )
        neg_inputs = model.tokenizer(
            qs, negs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )

        pos_inputs = {k: v.to(device) for k, v in pos_inputs.items()}
        neg_inputs = {k: v.to(device) for k, v in neg_inputs.items()}

        pos_scores = model.model(**pos_inputs).logits.squeeze(-1)
        neg_scores = model.model(**neg_inputs).logits.squeeze(-1)

        raw_loss = torch.nn.functional.softplus(neg_scores - pos_scores).mean()
        loss = raw_loss / grad_accum_steps
        loss.backward()

        if (global_step + 1) % grad_accum_steps == 0:
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

        epoch_loss += raw_loss.item()
        global_step += 1

    if (global_step % grad_accum_steps) != 0:
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad()
        
    print(f"epoch={epoch+1} avg_loss={epoch_loss/len(train_loader):.4f}")


model.save(OUTPUT_DIR)
print("Model saved to:", Path(OUTPUT_DIR).resolve())
