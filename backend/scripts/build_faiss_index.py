import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../backend
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer

from config import PROCESSED_DIR, INDEX_DIR, EMBED_MODEL_NAME, ensure_dirs
import torch
print("Device:", "cuda" if torch.cuda.is_available() else "cpu")



IN_GLOB = "chunks_part_*.parquet"

INDEX_PATH = INDEX_DIR / "chunks.faiss"
META_PATH = INDEX_DIR / "chunks_meta.parquet"

BATCH_SIZE = 512
ADD_BATCH_SIZE = 4096         # faiss add 的分块大小
PRINT_EVERY_PARTS = 1         # 每处理完多少个 parquet 分片打印一次
PRINT_EVERY_BATCHES = 200    # 每多少个 encode batch 打印一次

USE_COSINE = True  # cosine 相似度：向量归一化 + Inner Product

def main():
    ensure_dirs()

    part_files = sorted(PROCESSED_DIR.glob(IN_GLOB))
    if not part_files:
        raise FileNotFoundError(f"No parquet parts found: {PROCESSED_DIR / IN_GLOB}")

    print(f"Parquet parts: {len(part_files)}")
    print(f"Loading model: {EMBED_MODEL_NAME}")
    model = SentenceTransformer(EMBED_MODEL_NAME, device="cuda")

    index = None
    dim = None
    total_chunks = 0

    meta_out = []

    for pi, part_path in enumerate(part_files):
        df = pd.read_parquet(part_path)[["chunk_id", "doc_id", "text", "source"]]

    
        meta_out.append(df[["chunk_id", "doc_id", "source"]])

        texts = df["text"].astype(str).tolist()

        # 分批 encode -> 立即 add，不堆 vecs，不 vstack
        for bi in range(0, len(texts), BATCH_SIZE):
            batch = texts[bi:bi + BATCH_SIZE]

            emb = model.encode(
                batch,
                convert_to_numpy=True,
                show_progress_bar=False,
                batch_size=BATCH_SIZE,
                normalize_embeddings=USE_COSINE,   # 关键：省掉 faiss.normalize_L2
            ).astype("float32")

            if index is None:
                dim = emb.shape[1]
                index = faiss.IndexFlatIP(dim) if USE_COSINE else faiss.IndexFlatL2(dim)

            index.add(emb)

            total_chunks += len(batch)

            if bi == 0 or ((bi // BATCH_SIZE) % PRINT_EVERY_BATCHES == 0):
                print(f"[Part {pi+1}/{len(part_files)}] Encoded+Added {min(bi + BATCH_SIZE, len(texts))}/{len(texts)} in current part | Total {total_chunks}", flush=True)

        if (pi == 0) or ((pi + 1) % PRINT_EVERY_PARTS == 0):
            print(f"Finished part {pi+1}/{len(part_files)}: {part_path.name} | Total chunks so far: {total_chunks}", flush=True)

    if index is None or dim is None:
        raise RuntimeError("No vectors were added. Check your parquet parts content.")

    print("Writing index...")
    faiss.write_index(index, str(INDEX_PATH))

    print("Writing meta...")
    meta_df = pd.concat(meta_out, ignore_index=True)
    meta_df.to_parquet(META_PATH, index=False)

    print(f"Saved index: {INDEX_PATH}")
    print(f"Saved meta : {META_PATH}")
    print(f"Vectors: {index.ntotal}, dim: {dim}")

if __name__ == "__main__":
    main()
