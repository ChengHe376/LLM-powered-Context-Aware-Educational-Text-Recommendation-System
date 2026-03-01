import os
import re
import json
import time
import random
from typing import Dict, List, Tuple, Optional

import pymysql
import requests

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT") or 3306)
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DB = os.getenv("MYSQL_DB", "recsys")

FEEDBACK_TABLE = os.getenv("FEEDBACK_TABLE", "feedback_events")

# 你后端 /api/retrieve 的地址（用于补 hard negatives）
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# 导出文件
OUT_PAIRWISE = os.getenv("OUT_PAIRWISE", "pairwise_clicklike_v4.jsonl")
OUT_POINTWISE = os.getenv("OUT_POINTWISE", "pointwise_v4.jsonl")

# 召回候选数：用来挖 hard negative（越大越难，建议 20~50）
NEG_RETRIEVE_TOPN = int(os.getenv("NEG_RETRIEVE_TOPN", "50"))

# 每个正样本最多配几个负样本（控制数据量）
MAX_NEG_PER_POS = int(os.getenv("MAX_NEG_PER_POS", "8"))

# ===== impression-aware export =====
USE_IMPRESSION_NEG = os.getenv("USE_IMPRESSION_NEG", "1") == "1"
DWELL_POS_SEC = float(os.getenv("DWELL_POS_SEC", "10"))  # dwell>=10s 也可算弱正例（可调）
LIMIT_IMPRESSIONS = os.getenv("LIMIT_IMPRESSIONS")       # 例如 "2000"

CLICKLIKE_ONLY = os.getenv("CLICKLIKE_ONLY", "1") == "1"
INCLUDE_DISLIKE_AS_NEG = os.getenv("INCLUDE_DISLIKE_AS_NEG", "1") == "1"
DISABLE_HARD_NEG = os.getenv("DISABLE_HARD_NEG", "0") == "1"


# 请求间隔，避免把后端压垮
RETRIEVE_SLEEP_SEC = float(os.getenv("RETRIEVE_SLEEP_SEC", "0.03"))

# =========================
# 解析 query_text 前缀（与你模拟脚本一致）
# 形如：[sid=...][p=student][dom=cs] <raw query>
# =========================
PREFIX_RE = re.compile(
    r"^\[sid=(?P<sid>[^\]]+)\]\[p=(?P<p>[^\]]+)\]\[dom=(?P<dom>[^\]]+)\]\[policy=(?P<policy>[^\]]+)\]\s*(?P<raw>.*)$")

def parse_query_text(q: str) -> Tuple[str, str, str, str]:
    m = PREFIX_RE.match(q or "")
    if not m:
        raw = (q or "").strip()
        sid = f"nosid-{abs(hash(raw))}"
        return sid, "unknown", "unknown", raw
    return m.group("sid"), m.group("p"), m.group("dom"), (m.group("raw") or "").strip()


# =========================
# 与后端交互：取 hard negatives
# =========================
def retrieve_candidates(query_raw: str, topk: int) -> List[Dict]:
    payload = {
        "query": query_raw,
        "topk": topk,
        "include_text": True   # ← 新增这一行
    }
    r = requests.post(
        f"{BASE_URL}/api/retrieve",
        json=payload,
        timeout=(5, 180)
    )

    
    if r.status_code != 200:
        print("[WARN] /api/retrieve status =", r.status_code)
        print("[WARN] body(head) =", (r.text or "")[:500])
    
    r.raise_for_status()
    data = r.json()

    return data.get("results", [])


_TEXT_CACHE: Dict[str, Dict[str, str]] = {}  # query_raw -> {chunk_id: text}

def get_text_map_for_query(query_raw: str) -> Dict[str, str]:
    if query_raw in _TEXT_CACHE:
        return _TEXT_CACHE[query_raw]

    try:
        candidates = retrieve_candidates(query_raw, topk=NEG_RETRIEVE_TOPN)
    except Exception as e:
        print("[WARN] retrieve_candidates failed:", repr(e), "query_raw=", query_raw[:120])
        _TEXT_CACHE[query_raw] = {}
        return _TEXT_CACHE[query_raw]


    m: Dict[str, str] = {}
    for r in candidates:
        cid = str(r.get("chunk_id") or r.get("Id") or "")
        if not cid:
            continue

        txt = (r.get("text") or "").strip()
        if cid and txt:
            m[cid] = txt

    _TEXT_CACHE[query_raw] = m
    time.sleep(RETRIEVE_SLEEP_SEC)
    return m


# =========================
# label / reward 合成逻辑
# 你现有 feedback 里可能有 click/dwell/like/dislike
# 我们合成一个 pointwise label（0~3）和一个用于加权的 reward
# =========================
def compute_reward(has_click: bool, dwell: Optional[float], like: bool, dislike: bool) -> Tuple[float, int]:
    """
    reward: 连续值（后续可用于 sample weight）
    label: 离散等级 0~3（pointwise）
    """
    reward = 0.0
    if has_click:
        reward += 1.0
    if dwell is not None:
        # dwell 奖励做截断，避免极端值
        reward += min(max(dwell, 0.0), 120.0) / 60.0  # 最多 +2
    if like:
        reward += 1.0
    if dislike:
        reward -= 1.0

    # 离散 label（便于 pointwise/评估）
    if reward >= 2.2:
        label = 3
    elif reward >= 1.3:
        label = 2
    elif reward > 0.2:
        label = 1
    else:
        label = 0
    return reward, label

def persona_weight(persona: str) -> float:
    """
    训练权重：研究人员更“干净”，skimmer 噪声更大
    """
    p = (persona or "").lower()
    if p == "researcher":
        return 1.2
    if p == "student":
        return 1.0
    if p == "goal":
        return 1.1
    if p == "reader":
        return 0.9
    if p == "skimmer":
        return 0.6
    return 0.8

# =========================
# MySQL 读取
# =========================
def mysql_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

def fetch_impressions(conn) -> List[Dict]:
    limit_sql = f"LIMIT {int(LIMIT_IMPRESSIONS)}" if LIMIT_IMPRESSIONS else ""
    sql = f"""
    SELECT id, user_id, query_text, chunk_id, score, ts,
           impression_id, session_id, `rank`, policy, model_version, index_version
    FROM {FEEDBACK_TABLE}
    WHERE action = 'impression' AND impression_id IS NOT NULL
    ORDER BY id ASC
    {limit_sql}
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()

def fetch_actions_for_impression(conn, impression_id: str) -> List[Dict]:
    sql = f"""
    SELECT chunk_id, action, value
    FROM {FEEDBACK_TABLE}
    WHERE impression_id = %s
      AND action IN ('click', 'dwell', 'like', 'dislike')
    """
    with conn.cursor() as cur:
        cur.execute(sql, (impression_id,))
        return cur.fetchall()

def aggregate_chunk_feedback(rows: List[Dict]) -> Dict[str, Dict]:
    """
    return: {chunk_id: {"click":bool, "dwell":float|None, "like":bool, "dislike":bool}}
    """
    out: Dict[str, Dict] = {}
    for r in rows:
        cid = str(r.get("chunk_id"))
        a = (r.get("action") or "").lower()
        v = r.get("value")

        if cid not in out:
            out[cid] = {"click": False, "dwell": None, "like": False, "dislike": False}

        if a == "click":
            out[cid]["click"] = True
        elif a == "dwell" and v is not None:
            try:
                out[cid]["dwell"] = float(v)
            except Exception:
                pass
        elif a == "like":
            out[cid]["like"] = True
        elif a == "dislike":
            out[cid]["dislike"] = True
    return out

def is_positive(feat: Dict) -> bool:
    # v2：只用 click/like 当正例（对齐 --signal clicklike）
    if feat.get("click") or feat.get("like"):
        return True
    if CLICKLIKE_ONLY:
        return False

    # v1（保留兼容）：弱正例（可选）：dwell 达阈值且没 dislike
    dwell = feat.get("dwell")
    if dwell is not None and dwell >= DWELL_POS_SEC and not feat.get("dislike"):
        return True
    return False



# =========================
# 导出逻辑：click -> (pos, hard negs)
# =========================
def main():
    conn = mysql_conn()
    impressions = fetch_impressions(conn)
    if not impressions:
        raise RuntimeError("MySQL 中没有 impression 事件。请先跑模拟脚本并确保 /recommend 会写 impression。")

    # impression_id -> {meta + items[]}
    groups: Dict[str, Dict] = {}
    for row in impressions:
        imp = str(row.get("impression_id"))
        if not imp:
            continue
        g = groups.get(imp)
        if g is None:
            g = {
                "impression_id": imp,
                "user_id": str(row.get("user_id")),
                "query_text": str(row.get("query_text")),
                "session_id": row.get("session_id"),
                "policy": row.get("policy"),
                "model_version": row.get("model_version"),
                "index_version": row.get("index_version"),
                "items": []
            }
            groups[imp] = g

        g["items"].append({
            "chunk_id": str(row.get("chunk_id")),
            "score": row.get("score"),
            "rank": row.get("rank")
        })

    # 输出文件照旧
    pairwise_f = open(OUT_PAIRWISE, "w", encoding="utf-8")
    pointwise_f = open(OUT_POINTWISE, "w", encoding="utf-8")

    n_pair = 0
    n_point = 0
    n_pos_missing_text = 0
    n_neg_missing_text = 0
    n_empty_text_map = 0


    for imp_id, g in groups.items():
        user_id = g["user_id"]
        query_text = g["query_text"]
        sid, persona, domain, query_raw = parse_query_text(query_text)
        w = persona_weight(persona)

        # 该 impression 的后验行为聚合
        actions = fetch_actions_for_impression(conn, imp_id)
        feat_map = aggregate_chunk_feedback(actions)

        # 取文本映射（用于 pos_text/neg_text）
        text_map = get_text_map_for_query(query_raw)

        if not text_map:
            n_empty_text_map += 1


        # 划分正负
        pos_ids: List[str] = []
        neg_ids: List[str] = []

        for it in g["items"]:
            cid = it["chunk_id"]
            feat = feat_map.get(cid, {"click": False, "dwell": None, "like": False, "dislike": False})
            if is_positive(feat):
                pos_ids.append(cid)
            else:
                # v2：dislike 作为强负例（不再丢弃）
                if feat.get("dislike") and not INCLUDE_DISLIKE_AS_NEG:
                    continue
                neg_ids.append(cid)



            # pointwise：每个曝光项都写（label/reward基于其行为）
            reward, label = compute_reward(feat.get("click", False), feat.get("dwell"), feat.get("like", False), feat.get("dislike", False))
            point = {
                "query_id": imp_id,              # 现在用 impression_id 当 query_id 更合理
                "user_id": user_id,
                "persona": persona,
                "domain": domain,
                "query_text": query_raw,
                "query_text_full": query_text,
                "chunk_id": cid,
                "label": label,
                "reward": reward,
                "weight": w,
                "impression_id": imp_id,
                "rank": it.get("rank"),
                "label_source": "impression_aware"
            }
            pointwise_f.write(json.dumps(point, ensure_ascii=False) + "\n")
            n_point += 1

        # 如果没有正例，这个 impression 对 pairwise 没贡献（但 pointwise 仍有）
        if not pos_ids:
            continue

        base_neg_ids = neg_ids if USE_IMPRESSION_NEG else []

        for pos_cid in pos_ids:
            pos_text = (text_map.get(pos_cid) or "").strip()
            if not pos_text:
                n_pos_missing_text += 1
                continue

            hard_neg_ids = []
            if not DISABLE_HARD_NEG:
                try:
                    candidates = retrieve_candidates(query_raw, topk=NEG_RETRIEVE_TOPN)
                    for r in candidates:
                        cid = str(r.get("chunk_id") or "")
                        if not cid or cid == pos_cid:
                            continue

                        hard_neg_ids.append(cid)

                        txt = (r.get("text") or "").strip()
                        if txt:
                            text_map[cid] = txt
                except Exception as e:
                    print("[WARN] hard neg retrieve failed:", repr(e))


            # 合并：impression neg + hard neg（去重、排除 pos）
            cand_negs = []
            seen = set([pos_cid])

            for cid in base_neg_ids:
                if cid and cid not in seen:
                    cand_negs.append(cid)
                    seen.add(cid)

            for cid in hard_neg_ids:
                if cid and cid not in seen:
                    cand_negs.append(cid)
                    seen.add(cid)

            random.shuffle(cand_negs)
            cand_negs = cand_negs[:MAX_NEG_PER_POS]


            for neg_cid in cand_negs:
                neg_text = (text_map.get(neg_cid) or "").strip()
                if not neg_text:
                    n_neg_missing_text += 1
                    continue


                pair = {
                    "query_id": imp_id,
                    "user_id": user_id,
                    "persona": persona,
                    "domain": domain,
                    "query_text": query_raw,
                    "query_text_full": g["query_text"],
                    "pos_chunk_id": pos_cid,
                    "neg_chunk_id": neg_cid,
                    "pos_text": pos_text,
                    "neg_text": neg_text,
                    "weight": w,
                    "impression_id": imp_id,
                    "label_source": "impression_negative"
                }
                pairwise_f.write(json.dumps(pair, ensure_ascii=False) + "\n")
                n_pair += 1

    pairwise_f.close()
    pointwise_f.close()
    conn.close()

    print("debug:", "empty_text_map=", n_empty_text_map, "pos_missing_text=", n_pos_missing_text, "neg_missing_text=", n_neg_missing_text)
    print(f"exported pairwise: {n_pair} lines -> {OUT_PAIRWISE}")
    print(f"exported pointwise: {n_point} lines -> {OUT_POINTWISE}")


if __name__ == "__main__":
    main()
