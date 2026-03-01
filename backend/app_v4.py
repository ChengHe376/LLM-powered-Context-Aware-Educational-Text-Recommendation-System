from config import SECRET_KEY, APP_ENV, ensure_dirs, PROCESSED_DIR
import os

from flask import Flask, request, jsonify, session 
from flask_cors import CORS
import sys
import pandas as pd
from retrieval.faiss_retriever import FaissRetriever
from pathlib import Path

from services.db import Base, engine, SessionLocal
from services.models import FeedbackEvent
from sentence_transformers import CrossEncoder

import re
import uuid
import time

BASE_DIR = Path(__file__).resolve().parent  # backend 目录
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

RERANK_MODEL_DIR = Path(__file__).resolve().parent / "models" / "reranker" / "bge-reranker-v4"
reranker = None

app = Flask(__name__)
faiss_retriever = FaissRetriever(topk=5)
faiss_retriever.load()
Base.metadata.create_all(bind=engine)

ensure_dirs()
app.secret_key = SECRET_KEY
CORS(app, resources={r"/*": {"origins": ["http://localhost:5173"]}})


# Simulate user data
users = {
    "user1": {"password": "pass1", "user_id": "user1"},
    "user2": {"password": "pass2", "user_id": "user2"},
    "user3": {"password": "pass3", "user_id": "user3"},
    "user4": {"password": "pass4", "user_id": "user4"},
    "user5": {"password": "pass5", "user_id": "user5"}
}

CHUNKS_PATH = BASE_DIR / "data" / "processed" / "chunks.parquet"
CHUNKS_GLOB = "chunks_part_*.parquet"

def get_reranker():
    global reranker
    if reranker is not None:
        return reranker

    # Flask debug reloader: only load in the serving process
    if os.environ.get("FLASK_ENV") == "development" or os.environ.get("APP_ENV") == "dev":
        if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
            return None  # parent process, don't load

    reranker = CrossEncoder(str(RERANK_MODEL_DIR))
    return reranker

def load_chunks_df():
    # 1) 先尝试单文件 chunks.parquet
    if CHUNKS_PATH.exists():
        return pd.read_parquet(CHUNKS_PATH)

    # 2) 否则读取分片 chunks_part_*.parquet
    part_dir = CHUNKS_PATH.parent
    part_files = sorted(part_dir.glob(CHUNKS_GLOB))
    if not part_files:
        raise FileNotFoundError(
            f"chunks file not found: {CHUNKS_PATH} (and no parts matched {part_dir / CHUNKS_GLOB})"
        )

    # 注意：一次性 concat 会占内存；但你这里是后端服务启动时加载，通常可接受
    # 如果后续数据更大，再改成按 doc_id 懒加载
    dfs = []
    for p in part_files:
        dfs.append(pd.read_parquet(p))
    return pd.concat(dfs, ignore_index=True)


CHUNKS_DF = load_chunks_df()

# 统一把 doc_id 转为字符串，避免前后端类型不一致
CHUNKS_DF["doc_id"] = CHUNKS_DF["doc_id"].astype(str)
CHUNK_TEXT_MAP = dict(zip(CHUNKS_DF["chunk_id"].astype(str), CHUNKS_DF["text"].astype(str)))


# 从 doc_id 末尾提取数字序号（hf:...:<i>），用于正确排序
CHUNKS_DF["doc_num"] = (
    CHUNKS_DF["doc_id"]
    .astype(str)
    .str.extract(r":(\d+)$")[0]
    .astype("Int64")
)


if "order_in_doc" not in CHUNKS_DF.columns:
    CHUNKS_DF["order_in_doc"] = range(len(CHUNKS_DF))

if "chunk_id" not in CHUNKS_DF.columns:
    CHUNKS_DF["chunk_id"] = CHUNKS_DF.index.astype(str)

if "text" not in CHUNKS_DF.columns:
    CHUNKS_DF["text"] = ""

CHUNKS_SORTED = (
    CHUNKS_DF
    .sort_values(["doc_num", "order_in_doc"], kind="mergesort", na_position="last")
    .reset_index(drop=True)
)

# doc_id -> (start_idx, end_idx) in CHUNKS_SORTED，用于 O(1) 取书内容，避免每次全表过滤
DOC_RANGES = {}
_doc_ids = CHUNKS_SORTED["doc_id"].astype(str).tolist()
if _doc_ids:
    cur = _doc_ids[0]
    start = 0
    for i in range(1, len(_doc_ids)):
        if _doc_ids[i] != cur:
            DOC_RANGES[cur] = (start, i)
            cur = _doc_ids[i]
            start = i
    DOC_RANGES[cur] = (start, len(_doc_ids))



# 如果 order_in_doc 存在，尽量用于排序；否则用原始行序
HAS_ORDER = "order_in_doc" in CHUNKS_DF.columns

def build_docs_index(df: pd.DataFrame):
    # docs: [{doc_id, title, chunks_count, source, preview}]
    docs = []
    for doc_id, g in df.groupby("doc_id", sort=False):
        g_sorted = g.sort_values("order_in_doc") if HAS_ORDER else g

        source = ""
        if "source" in g_sorted.columns:
            v = g_sorted["source"].dropna()
            source = str(v.iloc[0]) if len(v) else ""

        # doc_title 为空就用 Document <doc_id>
        title = f"Document {doc_id}"
        if "doc_title" in g_sorted.columns:
            t = g_sorted["doc_title"].dropna().astype(str)
            if len(t) and t.iloc[0].strip():
                title = t.iloc[0].strip()

        preview = ""
        if "text" in g_sorted.columns:
            first_text = str(g_sorted["text"].iloc[0]) if len(g_sorted) else ""
            preview = first_text[:160]

        # 从 doc_id 末尾提取数字序号（如 hf:xxx:139298 → 139298）
        doc_num = None
        m = re.search(r":(\d+)$", str(doc_id))
        if m:
            doc_num = int(m.group(1))


        docs.append({
            "doc_id": doc_id,
            "doc_num": doc_num, 
            "title": title,
            "chunks_count": int(len(g_sorted)),
            "source": source,
            "preview": preview
        })
        
    docs.sort(key=lambda d: (d["doc_num"] is None, d["doc_num"]))
    return docs


DOCS_INDEX = build_docs_index(CHUNKS_DF)

PREFIX_RE = re.compile(r"^\[sid=(?P<sid>[^\]]+)\]\[p=(?P<p>[^\]]+)\]\[dom=(?P<dom>[^\]]+)\]\[policy=(?P<policy>[^\]]+)\]\s*(?P<raw>.*)$")

def strip_query_prefix(q: str) -> str:
    m = PREFIX_RE.match(q or "")
    if not m:
        return (q or "").strip()
    return (m.group("raw") or "").strip()

def _new_id():
    return uuid.uuid4().hex

def write_impressions(
    db,
    user_id: str,
    query_text: str,
    items: list,
    session_id: str = None,
    request_id: str = None,
    impression_id: str = None,
    policy: str = None,
    model_version: str = None,
    index_version: str = None,
    context: dict = None,
    latency_ms: int = None
):
    """
    items: [{chunk_id, score, rank, propensity(optional)}]
    """
    for it in items:
        evt = FeedbackEvent(
            user_id=user_id,
            query_text=query_text,
            chunk_id=str(it.get("chunk_id", "")),
            score=float(it.get("score")) if it.get("score") is not None else None,
            action="impression",
            value=1.0
        )

        evt.session_id = session_id
        evt.request_id = request_id
        evt.impression_id = impression_id
        evt.rank_pos = int(it["rank"]) if it.get("rank") is not None else None

        evt.policy = policy
        evt.model_version = model_version
        evt.index_version = index_version

        evt.context_json = {
            **(context or {}),
            "requested_policy": (context or {}).get("requested_policy"),
            "use_rerank": (context or {}).get("use_rerank"),
            "served_policy": policy,
            "served_model_version": model_version
        }

        evt.latency_ms = latency_ms
        evt.propensity = float(it["propensity"]) if it.get("propensity") is not None else None

        db.add(evt)



@app.route("/docs", methods=["GET"])
def get_docs():
    return jsonify({"docs": DOCS_INDEX}), 200

@app.route("/doc_content", methods=["GET"])
def get_doc_content():
    doc_id = request.args.get("doc_id")
    if not doc_id:
        return jsonify({"error": "Missing doc_id"}), 400

    doc_id = str(doc_id)
    rng = DOC_RANGES.get(doc_id)
    if not rng:
        return jsonify({"error": "Invalid doc_id"}), 400

    s0, e0 = rng
    total = e0 - s0

    try:
        start = int(request.args.get("start", 0))
    except:
        start = 0
    try:
        limit = int(request.args.get("limit", 200))
    except:
        limit = 200

    if start < 0:
        start = 0
    if limit <= 0:
        limit = 200
    if limit > 1000:
        limit = 1000

    page_start = s0 + start
    page_end = min(s0 + start + limit, e0)
    page_df = CHUNKS_SORTED.iloc[page_start:page_end]

    cols = ["chunk_id", "doc_id", "order_in_doc", "text", "text_len", "chapter", "section", "source"]
    exist_cols = [c for c in cols if c in page_df.columns]
    chunks = page_df[exist_cols].fillna("").to_dict(orient="records")

    next_start = start + len(page_df)
    has_more = next_start < total

    return jsonify({
        "doc_id": doc_id,
        "chunks": chunks,
        "start": start,
        "limit": limit,
        "next_start": next_start,
        "total": total,
        "has_more": has_more
    }), 200




@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.get_json(force=True) or {}

    user_id = (data.get("user_id") or "").strip()
    query_text = (data.get("query_text") or "").strip()
    chunk_id = (data.get("chunk_id") or "").strip()

    score = data.get("score")
    action = (data.get("action") or "click").strip()
    value = data.get("value")

    if not user_id or not query_text or not chunk_id:
        return jsonify({"ok": False, "error": "user_id, query_text, chunk_id are required"}), 400

    db = SessionLocal()
    try:
        evt = FeedbackEvent(
            user_id=user_id,
            query_text=query_text,
            chunk_id=chunk_id,
            score=float(score) if score is not None else None,
            action=action,
            value=float(value) if value is not None else None
        )
        
        
        session_id = (data.get("session_id") or "").strip() or None
        request_id = (data.get("request_id") or "").strip() or None
        impression_id = (data.get("impression_id") or "").strip() or None
        policy = (data.get("policy") or "").strip() or None
        model_version = (data.get("model_version") or "").strip() or None
        index_version = (data.get("index_version") or "").strip() or None

        rank = data.get("rank")
        context = data.get("context")  # dict or None
        latency_ms = data.get("latency_ms")
        propensity = data.get("propensity")

        evt.session_id = session_id
        evt.request_id = request_id
        evt.impression_id = impression_id
        evt.policy = policy
        evt.model_version = model_version
        evt.index_version = index_version

        evt.rank_pos = int(rank) if rank is not None else None
        evt.context_json = context if isinstance(context, dict) else None
        evt.latency_ms = int(latency_ms) if latency_ms is not None else None
        evt.propensity = float(propensity) if propensity is not None else None

        db.add(evt)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if username in users and users[username]["password"] == password:
        return jsonify({"message": "Login successful", "user_id": users[username]["user_id"]}), 200

    return jsonify({"error": "Invalid credentials"}), 401


@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id")
    query_text = data.get("query_text")
    query_raw = strip_query_prefix(query_text)

    session_id = (data.get("session_id") or "").strip() or None
    context = data.get("context") if isinstance(data.get("context"), dict) else None

    request_id = _new_id()
    impression_id = _new_id()

    requested_policy = (data.get("policy") or "faiss-only").strip()
    use_rerank = str(data.get("use_rerank", "false")).strip().lower() in ("1", "true", "yes")

    served_policy = "faiss+rerank" if use_rerank else "faiss-only"
    served_model_version = "bge-reranker-v4" if use_rerank else None
    index_version = (data.get("index_version") or "").strip() or None

    # === 关键改动：增强 context，用于写 impression ===
    context = {
        **(context or {}),
        "requested_policy": requested_policy,
        "use_rerank": use_rerank
    }


    if not user_id:
        return jsonify({"error": "No user_id provided"}), 400
    if not query_text:
        return jsonify({"error": "No query text provided"}), 400

    # FAISS TopK 召回
    t0 = time.time()
    topk = int(data.get("topk") or 5)
    results = faiss_retriever.retrieve(query_raw, topk=topk)


    latency_ms = int((time.time() - t0) * 1000)

    for r in results:
        if not r.get("text"):
            cid = str(r.get("chunk_id") or r.get("Id") or "")
            if cid:
                r["text"] = CHUNK_TEXT_MAP.get(cid, "")

    # 1) 如果 rerank 生效：写 rerank_score
    rr = get_reranker()
    if use_rerank and results and rr is not None:
        pairs = [(query_raw, r.get("text", "")) for r in results]
        scores = rr.predict(pairs)
        for r, s in zip(results, scores):
            r["rerank_score"] = float(s)

    # 2) 统一：按“最终用于展示/排序的分数”降序排序
    def final_score(x):
        return x.get("rerank_score", x.get("score", 0.0)) or 0.0

    results.sort(key=final_score, reverse=True)

    # 3) 统一：给 rank（faiss-only 也会有）
    for i, r in enumerate(results, start=1):
        r["rank"] = i




    # 兼容前端：recommendations 仍然是 [{Segment, Score}, ...]
    # recommendations: [{Id, Segment, Score}, ...]
    recs = [
        {
            "Id": r.get("chunk_id") or r.get("Id"),
            "Segment": r.get("text", ""),
            "Score": float(r.get("rerank_score", r.get("score", 0.0))),   # 用于排序/展示的主分数
            "FaissScore": float(r.get("score", 0.0)),                    # 召回分数
            "RerankScore": float(r.get("rerank_score")) if r.get("rerank_score") is not None else None,
            "Rank": int(r.get("rank") or 0)

        }
        for r in results
    ]

    db = SessionLocal()
    try:
        items = []
        for i, r in enumerate(results):
            cid = r.get("chunk_id") or r.get("Id")
            sc = r.get("score") if r.get("score") is not None else r.get("Score")

            items.append({
                "chunk_id": str(cid) if cid is not None else "",
                "score": float(sc) if sc is not None else None,
                "rank": int(r.get("rank") or (i + 1))
            })

        write_impressions(
            db=db,
            user_id=str(user_id),
            query_text=str(query_text),
            items=items,
            session_id=session_id,
            request_id=request_id,
            impression_id=impression_id,
            policy=served_policy,
            model_version=served_model_version,
            index_version=index_version,
            context=context,
            latency_ms=latency_ms
        )

        db.commit()
    finally:
        db.close()


    # 兼容前端图表：rec_contributions 给一个可用的结构（先用 FAISS 分数充当贡献）
    # 若你前端期望的是 dict，则返回 dict；若期望 list，也可改。
    rec_contributions = {
        "faiss_retrieval": [float(r.get("score", 0.0) or 0.0) for r in results]
    }

    return jsonify({
        "recommendations": recs,
        "rec_contributions": rec_contributions,
        "request_id": request_id,
        "impression_id": impression_id,
        "policy": served_policy,
        "model_version": served_model_version,
        "latency_ms": latency_ms
    })



@app.route("/stream", methods=["GET"])
def stream():
    limit = int(request.args.get("limit", 50))
    pos = request.args.get("pos")

    df = CHUNKS_SORTED  # 直接用预排序结果

    start = int(pos) if pos is not None else 0
    if start < 0:
        start = 0

    out = df.iloc[start:start + limit]

    chunks = out[["chunk_id", "doc_id", "order_in_doc", "text"]].fillna("").to_dict(orient="records")

    next_pos = start + len(out)
    next_cursor = None
    if next_pos < len(df):
        next_cursor = {"pos": next_pos}

    return jsonify({"chunks": chunks, "next": next_cursor}), 200


# 优化检索路由
@app.route("/api/retrieve", methods=["POST"])
def api_retrieve():
    data = request.get_json(force=True) or {}
    query = (data.get("query") or "").strip()
    topk = int(data.get("topk") or 5)
    include_text = bool(data.get("include_text", False))

    

    if not query:
        return jsonify({"ok": False, "error": "query is required"}), 400

    results = faiss_retriever.retrieve(query, topk=topk)

    if include_text:
        for r in results:
            cid = str(r.get("chunk_id") or r.get("Id") or "")
            if not cid:
                continue

            if not r.get("text"):
                # 优先用已有字段
                if r.get("Segment"):
                    r["text"] = r["Segment"]
                elif r.get("chunk_text"):
                    r["text"] = r["chunk_text"]
                else:
                    # 最稳：从本地 chunks 数据补全文本
                    r["text"] = CHUNK_TEXT_MAP.get(cid, "")


    return jsonify({"ok": True, "query": query, "results": results})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=(APP_ENV == "dev"), threaded=True)


