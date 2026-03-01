import sys
from pathlib import Path

# 确保能 import config（Windows 下从 scripts 运行需要这一段）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re
import hashlib
import pandas as pd
from datasets import load_from_disk

from config import RAW_DIR, PROCESSED_DIR, ensure_dirs

# 你刚刚保存的 HF 数据集目录名
HF_SAVE_DIR = "hf_izumi-lab__open-text-books"

# 字段名（你输出里就是 text）
TEXT_FIELD = "text"

# 切分参数：按字符长度近似 token（先跑通，后面可换 tokenizer）
CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150

def normalize_ws(s: str) -> str:
    if not s:
        return ""

    # 统一换行
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # 去掉每行行尾空白（避免很多“伪空格”）
    s = "\n".join(line.rstrip() for line in s.split("\n"))

    # 把行内的连续空格/tab 压成 1 个空格（不动换行）
    s = re.sub(r"[ \t\f\v]+", " ", s)

    # 3 个以上换行压成 2 个（保留段落空行）
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def chunk_text(text: str, size: int, overlap: int):
    text = normalize_ws(text)
    if not text:
        return

    SENT_END_RE = re.compile(r"(.+?[。！？；!?;]+)(?=\s|$)")
    FALLBACK_SPLIT_RE = re.compile(r"(\n\n+|\n)")

    def split_into_paragraphs(t: str):
        for p in re.split(r"\n\s*\n", t):
            p = p.strip()
            if p:
                yield p

    def split_into_sentences(p: str):
        p = p.strip()
        if not p:
            return
        sents = [m.group(1).strip() for m in SENT_END_RE.finditer(p)]
        if sents:
            tail = p
            for s in sents:
                idx = tail.find(s)
                if idx >= 0:
                    tail = tail[idx + len(s):]
            tail = tail.strip()
            for s in sents:
                if s:
                    yield s
            if tail:
                yield tail
            return

        parts = [x.strip() for x in FALLBACK_SPLIT_RE.split(p) if x and x.strip()]
        buf = ""
        for x in parts:
            if len(buf) + (1 if buf else 0) + len(x) <= max(64, size // 3):
                buf = f"{buf} {x}".strip() if buf else x
            else:
                if buf:
                    yield buf
                buf = x
        if buf:
            yield buf

    def units_len(us):
        # 不 join，直接累计，避免产生大量临时大字符串
        total = 0
        first = True
        has_para = False
        for u in us:
            if u == "\n\n":
                has_para = True
                continue
            if not u:
                continue
            if first:
                total += len(u)
                first = False
            else:
                total += 1 + len(u)
        if has_para:
            total += 2
        return total

    def join_units(us):
        out = []
        for u in us:
            if u == "\n\n":
                if out and out[-1].endswith(" "):
                    out[-1] = out[-1].rstrip()
                out.append("\n\n")
            else:
                if not out:
                    out.append(u)
                else:
                    if out[-1].endswith("\n\n"):
                        out.append(u)
                    else:
                        out.append(" " + u)
        return "".join(out).strip()

    def build_overlap_units(prev_units, overlap_chars: int):
        if overlap_chars <= 0:
            return []
        tail = []
        acc = 0
        for u in reversed(prev_units):
            if u == "\n\n":
                if tail and tail[0] != "\n\n":
                    tail.insert(0, "\n\n")
                continue
            tail.insert(0, u)
            acc += len(u) + 1
            if acc >= overlap_chars:
                break
        return tail

    # 注意：这里不再构造 units 的巨大列表，而是“边遍历边组块”
    cur = []
    first_para = True

    def flush_cur():
        nonlocal cur
        while cur and cur[-1] == "\n\n":
            cur.pop()
        if not cur:
            return None
        return join_units(cur)

    for p in split_into_paragraphs(text):
        if not first_para:
            u = "\n\n"
            trial = cur + [u]
            if units_len(trial) <= size or not cur:
                cur = trial
            else:
                chunk = flush_cur()
                if chunk:
                    yield chunk
                ov = build_overlap_units(cur, overlap)
                cur = ov[:]
                cur.append("\n\n")
        first_para = False

        for s in split_into_sentences(p):
            u = s
            trial = cur + [u]
            if units_len(trial) <= size or not cur:
                cur = trial
                continue

            chunk = flush_cur()
            if chunk:
                yield chunk

            ov = build_overlap_units(cur, overlap)
            cur = ov[:]
            cur.append(u)

    last = flush_cur()
    if last:
        yield last


def make_chunk_id(doc_id: str, order_in_doc: int, text: str) -> str:
    h = hashlib.sha1()
    h.update(doc_id.encode("utf-8"))
    h.update(b"|")
    h.update(str(order_in_doc).encode("utf-8"))
    h.update(b"|")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]

def main():
    ensure_dirs()

    ds_path = RAW_DIR / HF_SAVE_DIR
    if not ds_path.exists():
        raise FileNotFoundError(f"HF dataset not found: {ds_path}")

    ds = load_from_disk(str(ds_path))
    if "train" not in ds:
        raise ValueError(f"Expected split 'train'. Found: {list(ds.keys())}")

    train = ds["train"]
    if TEXT_FIELD not in train.column_names:
        raise ValueError(f"Missing field '{TEXT_FIELD}'. Found: {train.column_names}")

    # 分批写盘，避免 rows 全量堆内存
    BUFFER_ROWS = 5000
    buf = []
    part_idx = 0
    global_order = 0

    def flush_buf():
        nonlocal part_idx
        if not buf:
            return
        out_path = PROCESSED_DIR / f"chunks_part_{part_idx:05d}.parquet"
        pd.DataFrame(buf).to_parquet(out_path, index=False)
        buf.clear()
        part_idx += 1

    for i in range(len(train)):
        raw_text = train[i][TEXT_FIELD]
        if raw_text is None:
            continue
        raw_text = str(raw_text)
        # 注意：不要在 main 里 normalize 两次，chunk_text 内部会 normalize
        raw_text = raw_text.strip()
        if not raw_text:
            continue

        doc_id = f"hf:{HF_SAVE_DIR}:{i}"

        for part in chunk_text(raw_text, CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS):
            global_order += 1
            chunk_id = make_chunk_id(doc_id, global_order, part)
            buf.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "doc_title": "",
                "chapter": "",
                "section": "",
                "order_in_doc": global_order,
                "text": part,
                "text_len": len(part),
                "source": f"{HF_SAVE_DIR}#train[{i}]",
            })

            if len(buf) >= BUFFER_ROWS:
                flush_buf()

        if i == 0 or (i % 200 == 0):
            print(f"Processed docs {i}/{len(train)}", flush=True)

    flush_buf()

    print(f"Saved parquet parts to: {PROCESSED_DIR}", flush=True)
    print(f"Example: chunks_part_00000.parquet ... chunks_part_{max(0, part_idx-1):05d}.parquet", flush=True)
    print(f"Total chunks: {global_order}", flush=True)


if __name__ == "__main__":
    main()
