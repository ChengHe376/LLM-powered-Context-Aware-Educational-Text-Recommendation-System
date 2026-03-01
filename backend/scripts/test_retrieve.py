import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer

from config import INDEX_DIR, PROCESSED_DIR, EMBED_MODEL_NAME

INDEX_PATH = INDEX_DIR / "chunks.faiss"
META_PATH = INDEX_DIR / "chunks_meta.parquet"

CHUNKS_PATH = PROCESSED_DIR / "chunks.parquet"
CHUNKS_GLOB = "chunks_part_*.parquet"

TOPK = 5

def main():
    if not INDEX_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("Index/meta not found. Run build_faiss_index.py first.")

    index = faiss.read_index(str(INDEX_PATH))
    meta = pd.read_parquet(META_PATH)

    # 如果 meta 不含 text，就从 chunks.parquet / chunks_part_*.parquet 补齐
    if "text" not in meta.columns:
        if CHUNKS_PATH.exists():
            chunks_df = pd.read_parquet(CHUNKS_PATH, columns=["chunk_id", "text"])
        else:
            part_files = sorted(PROCESSED_DIR.glob(CHUNKS_GLOB))
            if not part_files:
                raise FileNotFoundError(f"Missing chunks data: {CHUNKS_PATH} or {CHUNKS_GLOB}")
            chunks_df = pd.concat(
                (pd.read_parquet(p, columns=["chunk_id", "text"]) for p in part_files),
                ignore_index=True
            )

        meta = meta.merge(chunks_df, on="chunk_id", how="left")

        if meta["text"].isna().any():
            raise ValueError("Some texts are missing after merge. Check chunk_id consistency between meta and chunks.")


    model = SentenceTransformer(EMBED_MODEL_NAME)

    while True:
        query = input("\nQuery (empty to quit): ").strip()
        if not query:
            break

        q = model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(q)

        scores, ids = index.search(q, TOPK)
        ids = ids[0]
        scores = scores[0]

        for rank, (idx, sc) in enumerate(zip(ids, scores), start=1):
            row = meta.iloc[int(idx)]
            print("=" * 90)
            print(f"Rank {rank} | score={float(sc):.4f} | source={row['source']}")
            print(row["text"][:700])

if __name__ == "__main__":
    main()
