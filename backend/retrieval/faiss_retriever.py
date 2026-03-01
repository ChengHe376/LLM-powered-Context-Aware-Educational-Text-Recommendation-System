import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer

from config import INDEX_DIR, PROCESSED_DIR, EMBED_MODEL_NAME

import torch
import time

print("[DEBUG] imported faiss_retriever from:", __file__, flush=True)


class FaissRetriever:
    def __init__(self, topk: int = 5):
        self.topk = topk
        self._index = None
        self._meta = None
        self._model_name = EMBED_MODEL_NAME
        self._model = None
        self._text_map = None
        self._loaded = False



    def load(self):
        if self._loaded:
            return

        index_path = INDEX_DIR / "chunks.faiss"
        meta_path = INDEX_DIR / "chunks_meta.parquet"

        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError("FAISS index or meta file not found. Build index first.")

        t0 = time.time()
        self._index = faiss.read_index(str(index_path))
        print("[faiss] read_index:", time.time() - t0)


        
        t0 = time.time()
        self._meta = pd.read_parquet(meta_path)
        print("[faiss] read_meta:", time.time() - t0)

        # 确保 meta 至少有 chunk_id / doc_id
        need_cols = {"chunk_id", "doc_id"}
        if not need_cols.issubset(set(self._meta.columns)):
            raise ValueError(f"Meta missing columns: {need_cols - set(self._meta.columns)}")

        # 如果 meta 不含 text：从 processed/chunks.parquet 或分片构建 text_map
        if "text" not in self._meta.columns:
            chunks_path = PROCESSED_DIR / "chunks.parquet"
            if chunks_path.exists():
                chunks_df = pd.read_parquet(chunks_path, columns=["chunk_id", "text"])
            else:
                part_files = sorted(PROCESSED_DIR.glob("chunks_part_*.parquet"))
                if not part_files:
                    raise FileNotFoundError(
                        f"Missing chunks data: {chunks_path} or chunks_part_*.parquet in {PROCESSED_DIR}"
                    )
                chunks_df = pd.concat(
                    (pd.read_parquet(p, columns=["chunk_id", "text"]) for p in part_files),
                    ignore_index=True
                )

            # 用 dict 查 text：更省内存也更快，不必把 text merge 回 meta
            self._text_map = dict(
                zip(chunks_df["chunk_id"].astype(str), chunks_df["text"].astype(str))
            )
        else:
            self._text_map = None

        device = "cuda" if torch.cuda.is_available() else "cpu"
        t0 = time.time()
        self._model = SentenceTransformer(self._model_name, device=device)
        print("[faiss] load_model:", time.time() - t0)
        self._loaded = True




    def retrieve(self, query: str, topk: int | None = None):
        print("[DEBUG] FaissRetriever.retrieve called", flush=True)
        print("[DEBUG] query:", query[:80], flush=True)

        if self._index is None:
            self.load()

        k = topk or self.topk
        q = self._model.encode([query], convert_to_numpy=True).astype("float32")
        faiss.normalize_L2(q)

        scores, ids = self._index.search(q, k)
        ids = ids[0].tolist()
        scores = scores[0].tolist()

        results = []
        for idx, score in zip(ids, scores):
            row = self._meta.iloc[int(idx)]
            results.append({
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "source": row.get("source", ""),
                "score": float(score),
                "text": (row["text"] if "text" in row.index else (self._text_map.get(str(row["chunk_id"]), "") if self._text_map else "")),
            })
        
        print("[DEBUG] results size:", len(results), flush=True)
        if results:
            print("[DEBUG] first text len:", len(results[0].get("text") or ""), "chunk_id:", results[0].get("chunk_id"), flush=True)

        return results
