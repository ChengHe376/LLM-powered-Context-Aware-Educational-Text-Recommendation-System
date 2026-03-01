import random
import time
import math
import requests
import uuid

def new_session_id():
    return uuid.uuid4().hex


# =========================
# 基础配置
# =========================
BASE_URL = "http://localhost:5000"  
TOPK = 5
N_EVENTS = 800                       # 总“查询轮次”数量（不是 feedback 行数）
SLEEP_BETWEEN_SESSIONS = (5, 25)     # session 间休息秒数区间

# 账号 -> 画像（最终版固定映射）
USER_PERSONA_MAP = {
    "user1": "student",
    "user2": "reader",
    "user3": "researcher",
    "user4": "skimmer",
    "user5": "goal",
}

# 账号 -> 领域偏好（可按你数据集实际内容随便调）
USER_FOCUS_DOMAIN_MAP = {
    "user1": "cs",
    "user2": None,
    "user3": "ml",
    "user4": None,
    "user5": "stats",
}

USERS = list(USER_PERSONA_MAP.keys())

# =========================
# 领域关键词与模板（按画像区分）
# =========================
KEYWORDS_BY_DOMAIN = {
    "math": ["matrix", "eigenvalue", "derivative", "integral", "optimization"],
    "ml": ["gradient", "loss function", "regularization", "overfitting", "classification"],
    "stats": ["regression", "probability", "bayes", "hypothesis testing", "confidence interval"],
    "cs": ["algorithm", "complexity", "data structure", "recursion", "hashing"],
}

TEMPLATES = {
    "reader": [
        "summarize {kw} with intuition",
        "give an interesting example of {kw}",
        "how does {kw} relate to real life",
        "explain {kw} in simple words",
    ],
    "student": [
        "what is {kw}",
        "difference between {kw} and {kw2}",
        "{kw} definition and examples",
        "explain {kw} with a worked example",
        "common mistakes about {kw}",
    ],
    "researcher": [
        "{kw} formal definition",
        "{kw} assumptions and limitations",
        "derive {kw} step by step",
        "compare {kw} vs {kw2} theoretically",
        "state-of-the-art methods for {kw}",
    ],
    "skimmer": [
        "{kw} quick summary",
        "{kw} key points",
        "{kw} in 3 bullets",
        "tl;dr {kw}",
    ],
    "goal": [
        "I need to understand {kw} to solve a problem",
        "teach me {kw} step-by-step with example",
        "how to apply {kw} in practice",
        "give me a concise study guide for {kw}",
    ],
}

# =========================
# 画像参数（点击/停留/反馈分布 + query 来源 + topic 专注度）
# =========================
PERSONAS = {
    "reader": {
        "p_click_any": 0.72,
        "softmax_tau": 0.18,
        "rank_bias_w": 0.18,
        "score_w": 1.00,
        "p_like_after_click": 0.35,
        "p_dislike_after_click": 0.06,
        "dwell_mu": 18,
        "dwell_sigma": 10,
        "query_mode": {"context": 0.60, "template": 0.40},
        "topic_focus": 0.35,
    },
    "student": {
        "p_click_any": 0.65,
        "softmax_tau": 0.12,
        "rank_bias_w": 0.28,
        "score_w": 1.00,
        "p_like_after_click": 0.45,
        "p_dislike_after_click": 0.08,
        "dwell_mu": 28,
        "dwell_sigma": 14,
        "query_mode": {"context": 0.45, "template": 0.55},
        "topic_focus": 0.55,
    },
    "researcher": {
        "p_click_any": 0.52,
        "softmax_tau": 0.08,
        "rank_bias_w": 0.10,
        "score_w": 1.20,
        "p_like_after_click": 0.22,
        "p_dislike_after_click": 0.18,
        "dwell_mu": 55,
        "dwell_sigma": 22,
        "query_mode": {"context": 0.30, "template": 0.70},
        "topic_focus": 0.80,
    },
    "skimmer": {
        "p_click_any": 0.78,
        "softmax_tau": 0.20,
        "rank_bias_w": 0.35,
        "score_w": 0.90,
        "p_like_after_click": 0.08,
        "p_dislike_after_click": 0.10,
        "dwell_mu": 6,
        "dwell_sigma": 4,
        "query_mode": {"context": 0.25, "template": 0.75},
        "topic_focus": 0.20,
    },
    "goal": {
        "p_click_any": 0.68,
        "softmax_tau": 0.10,
        "rank_bias_w": 0.22,
        "score_w": 1.10,
        "p_like_after_click": 0.40,
        "p_dislike_after_click": 0.07,
        "dwell_mu": 40,
        "dwell_sigma": 18,
        "query_mode": {"context": 0.40, "template": 0.60},
        "topic_focus": 0.75,
    },
}

# session 参数：长度、查询间隔、换主题概率
SESSION_CFG = {
    "reader": {"len_min": 3, "len_max": 8,  "gap_mu": 6,  "gap_sigma": 4,  "p_same_topic": 0.55},
    "student": {"len_min": 4, "len_max": 10, "gap_mu": 9,  "gap_sigma": 6,  "p_same_topic": 0.70},
    "researcher": {"len_min": 5, "len_max": 14, "gap_mu": 14, "gap_sigma": 9,  "p_same_topic": 0.85},
    "skimmer": {"len_min": 2, "len_max": 6,  "gap_mu": 3,  "gap_sigma": 2,  "p_same_topic": 0.35},
    "goal": {"len_min": 5, "len_max": 12, "gap_mu": 8,  "gap_sigma": 5,  "p_same_topic": 0.82},
}

# =========================
# HTTP 调用
# =========================
def get_docs():
    r = requests.get(f"{BASE_URL}/docs", timeout=(5, 180))
    if r.status_code >= 400:
        print("STATUS:", r.status_code)
        print("BODY:", r.text[:2000])
    r.raise_for_status()
    return r.json()["docs"]

def get_doc_chunks(doc_id, start=0, limit=200):
    r = requests.get(f"{BASE_URL}/doc_content", params={"doc_id": doc_id, "start": start, "limit": limit}, timeout=(5, 180))
    if r.status_code >= 400:
        print("STATUS:", r.status_code)
        print("BODY:", r.text[:2000])
    r.raise_for_status()

    return r.json()["chunks"]

def recommend(user_id, query_text, session_id, topk=TOPK, use_rerank=True):
    payload = {
        "user_id": user_id,
        "query_text": query_text,
        "topk": topk,
        "session_id": session_id,
        "use_rerank": use_rerank,
        "policy": "faiss+rerank" if use_rerank else "faiss-only"
    }
    r = requests.post(f"{BASE_URL}/recommend", json=payload, timeout=(5, 180))
    if r.status_code >= 400:
        print("STATUS:", r.status_code)
        print("BODY:", r.text[:2000])
    r.raise_for_status()
    return r.json()


def send_feedback(user_id, query_text, chunk_id, score, action, value, session_id=None, impression_id=None, rank=None):
    payload = {
    "user_id": user_id,
    "query_text": query_text,
    "chunk_id": str(chunk_id),
    "score": float(score) if score is not None else None,
    "action": action,
    "value": value,
    "session_id": session_id,
    "impression_id": impression_id,
    "rank": rank
    }

    r = requests.post(f"{BASE_URL}/feedback", json=payload, timeout=(5, 180))
    if r.status_code >= 400:
        print("STATUS:", r.status_code)
        print("BODY:", r.text[:2000])
    r.raise_for_status()

    return r.json()

# =========================
# 行为模型工具函数
# =========================
def softmax(xs, tau):
    m = max(xs)
    exps = [math.exp((x - m) / max(tau, 1e-6)) for x in xs]
    s = sum(exps)
    return [e / s for e in exps]

def choose_click(results, cfg):
    if not results:
        return None

    if random.random() > cfg["p_click_any"]:
        return None

    scores = [float(r.get("score", 0.0)) for r in results]
    rank_bias = [1.0 / (1.0 + i) for i in range(len(results))]
    mixed = [cfg["score_w"] * s + cfg["rank_bias_w"] * b for s, b in zip(scores, rank_bias)]
    probs = softmax(mixed, tau=cfg["softmax_tau"])
    idx = random.choices(range(len(results)), weights=probs, k=1)[0]
    return results[idx]

def sample_dwell(cfg):
    x = random.gauss(cfg["dwell_mu"], cfg["dwell_sigma"])
    return max(6, int(x))

def sample_session_len(sc):
    return random.randint(sc["len_min"], sc["len_max"])

def sample_gap(sc):
    x = random.gauss(sc["gap_mu"], sc["gap_sigma"])
    return max(1, int(x))

def pick_domain(focus_domain, cfg):
    # topic_focus 越高，越偏向固定领域
    if focus_domain is not None:
        return focus_domain
    if random.random() < cfg["topic_focus"]:
        return random.choice(list(KEYWORDS_BY_DOMAIN.keys()))
    return random.choice(list(KEYWORDS_BY_DOMAIN.keys()))

def maybe_switch_domain(domain, sc):
    if random.random() < sc["p_same_topic"]:
        return domain
    return random.choice([d for d in KEYWORDS_BY_DOMAIN.keys() if d != domain])

def pick_kw(domain):
    kws = KEYWORDS_BY_DOMAIN[domain]
    kw = random.choice(kws)
    kw2 = random.choice([x for x in kws if x != kw]) if len(kws) > 1 else kw
    return kw, kw2

def build_query_template(persona, domain):
    kw, kw2 = pick_kw(domain)
    tpl = random.choice(TEMPLATES[persona])
    return tpl.format(kw=kw, kw2=kw2)

def build_query_from_chunk(chunks):
    c = random.choice(chunks)
    text = (c.get("text") or "").strip().replace("\n", " ")
    if len(text) > 160:
        text = text[:160]
    prefix = random.choice(["Explain: ", "Summarize: ", "What does this mean: ", ""])
    return prefix + text

# =========================
# 主流程：五画像 + session
# =========================
def run():
    docs = get_docs()


    # 预取少量 docs 的前 200 chunks，避免脚本过程中频繁拉取
    sampled = random.sample(docs, k=min(6, len(docs)))
    cache = {}
    for d in sampled:
        doc_id = str(d["doc_id"])
        chunks = get_doc_chunks(doc_id, start=0, limit=200)
        if chunks:
            cache[doc_id] = chunks

    doc_ids = list(cache.keys())
    if not doc_ids:
        raise RuntimeError("无法从 /doc_content 拉到 chunks，请检查后端是否加载了数据集")

    done = 0
    while done < N_EVENTS:
        user_id = random.choice(USERS)
        persona = USER_PERSONA_MAP[user_id]
        cfg = PERSONAS[persona]
        sc = SESSION_CFG[persona]

        focus_domain = USER_FOCUS_DOMAIN_MAP.get(user_id)
        domain = pick_domain(focus_domain, cfg)

        session_id = f"{user_id}-{int(time.time()*1000)}-{random.randint(1000,9999)}"
        use_rerank = (random.random() < 0.5)   # 50% rerank, 50% faiss-only
        session_len = sample_session_len(sc)

        for _ in range(session_len):
            if done >= N_EVENTS:
                break

            domain = maybe_switch_domain(domain, sc)

            # 选择 query 来源：context vs template
            if random.random() < cfg["query_mode"]["context"]:
                doc_id = random.choice(doc_ids)
                query_raw = build_query_from_chunk(cache[doc_id])
            else:
                query_raw = build_query_template(persona, domain)

            # 用 raw query 检索（避免前缀影响语义）
            rec_resp = recommend(
                user_id,
                query_raw,
                session_id,
                topk=TOPK,
                use_rerank=use_rerank
            )

            recs = rec_resp.get("recommendations", [])
            impression_id = rec_resp.get("impression_id")
            # 为了复用 choose_click，把 recs 转成与原 results 类似结构
            results = [{"chunk_id": r["Id"], "score": r.get("FaissScore", r.get("Score"))} for r in recs]
            clicked = choose_click(results, cfg)


            # 发送到 feedback 的 query_text 带上 sid/persona/domain，便于离线解析 session
            query_to_log = (
                f"[sid={session_id}]"
                f"[p={persona}]"
                f"[dom={domain}]"
                f"[policy={'faiss+rerank' if use_rerank else 'faiss-only'}]"
                f"{query_raw}"
            )


            if clicked is not None:
                # 找到 clicked 在列表里的 rank（1-based）
                clicked_rank = None
                for i, it in enumerate(results):
                    if str(it["chunk_id"]) == str(clicked["chunk_id"]):
                        clicked_rank = i + 1
                        break

                send_feedback(
                    user_id, query_to_log, clicked["chunk_id"], clicked.get("score"),
                    "click", 1.0,
                    session_id=session_id, impression_id=impression_id, rank=clicked_rank
                )

                dwell = sample_dwell(cfg)
                send_feedback(
                    user_id, query_to_log, clicked["chunk_id"], clicked.get("score"),
                    "dwell", float(dwell),
                    session_id=session_id, impression_id=impression_id, rank=clicked_rank
                )

                r = random.random()
                if r < cfg["p_like_after_click"]:
                    send_feedback(
                        user_id, query_to_log, clicked["chunk_id"], clicked.get("score"), "like", 1.0,
                        session_id=session_id, impression_id=impression_id, rank=clicked_rank
                    )
                elif r < cfg["p_like_after_click"] + cfg["p_dislike_after_click"]:
                    send_feedback(
                        user_id, query_to_log, clicked["chunk_id"], clicked.get("score"), "dislike", 1.0,
                        session_id=session_id, impression_id=impression_id, rank=clicked_rank
                    )

            time.sleep(sample_gap(sc))
            done += 1

        time.sleep(random.randint(*SLEEP_BETWEEN_SESSIONS))

    print(f"done: {N_EVENTS} query rounds simulated across 5 personas")

if __name__ == "__main__":
    run()
