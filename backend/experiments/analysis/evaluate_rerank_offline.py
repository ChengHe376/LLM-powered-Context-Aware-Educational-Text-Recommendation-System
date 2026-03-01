# evaluate_rerank_offline.py
# Offline evaluation for rerank policies using MySQL feedback_events
# Metrics: NDCG@K, MRR@K (per impression_id), grouped by policy

import os
import math
import argparse
from collections import defaultdict

def get_db_conn():
    """
    Tries PyMySQL first, then mysql-connector-python.
    Required env vars (recommended):
      MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB
    """
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "yourPassword")
    db = os.environ.get("MYSQL_DB", "recsys")

    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        return conn, "pymysql"
    except Exception:
        pass

    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
        )
        return conn, "mysql.connector"
    except Exception as e:
        raise RuntimeError(
            "Cannot connect to MySQL. Install pymysql or mysql-connector-python, "
            "and set MYSQL_HOST/MYSQL_PORT/MYSQL_USER/MYSQL_PASSWORD/MYSQL_DB."
        ) from e


def fetch_impressions(conn, driver, days=7, since=None, until=None, max_impressions=5000, policies=None, model_version=None):

    """
    Fetch impressions within last N days (by ts).
    Returns:
      impressions: list of dict {impression_id, policy, chunk_id, rank, ts}
    """
    time_clauses = []
    time_params = []

    if since:
        time_clauses.append("ts >= %s")
        time_params.append(since)

    if until:
        time_clauses.append("ts < %s")
        time_params.append(until)

    if not time_clauses:
        time_clauses.append("ts >= (NOW() - INTERVAL %s DAY)")
        time_params.append(days)

    time_clause = "AND " + " AND ".join(time_clauses)


    if model_version:
        mv_clause = "AND model_version = %s"
        mv_params = [model_version]
    else:
        mv_clause = ""
        mv_params = []


    if policies:
        placeholders = ",".join(["%s"] * len(policies))
        policy_clause = f"AND policy IN ({placeholders})"
        params = time_params + mv_params + list(policies) + [max_impressions]
    else:
        policy_clause = ""
        params = time_params + mv_params + [max_impressions]

    sql = f"""
    SELECT impression_id, policy, chunk_id, `rank` AS rank_pos, ts
    FROM feedback_events
    WHERE action='impression'
    AND impression_id IS NOT NULL
    {time_clause}
    {mv_clause}
    {policy_clause}
    ORDER BY ts DESC
    LIMIT %s
    """

    cur = conn.cursor(dictionary=True) if driver == "mysql.connector" else conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()

    # Normalize to list[dict]
    if driver == "mysql.connector":
        impressions = rows
    else:
        impressions = list(rows)

    # Filter invalid
    impressions = [
        r for r in impressions
        if r.get("impression_id") and r.get("chunk_id") and r.get("rank_pos") is not None
    ]
    return impressions


def fetch_actions(conn, driver, impression_ids, days=7, since=None, until=None):


    """
    Fetch actions (click/like/dwell/dislike) for given impression_ids.
    Returns:
      actions_map[(impression_id, chunk_id)] -> dict of aggregated signals
    """
    if not impression_ids:
        return {}

    # Chunk query to avoid overly long IN clause
    BATCH = 800
    actions_map = {}

    def update_signal(key, action, value):
        agg = actions_map.get(key)
        if agg is None:
            agg = {"click": 0, "like": 0, "dislike": 0, "dwell": 0.0, "dwell_max": 0.0}
            actions_map[key] = agg

        if action == "click":
            agg["click"] += 1
        elif action == "like":
            agg["like"] += 1
        elif action == "dislike":
            agg["dislike"] += 1
        elif action == "dwell":
            v = float(value or 0.0)
            agg["dwell"] += v
            if v > agg["dwell_max"]:
                agg["dwell_max"] = v

    time_clauses = []
    time_params = []

    if since:
        time_clauses.append("ts >= %s")
        time_params.append(since)

    if until:
        time_clauses.append("ts < %s")
        time_params.append(until)

    if not time_clauses:
        time_clauses.append("ts >= (NOW() - INTERVAL %s DAY)")
        time_params.append(days)

    time_clause = "AND " + " AND ".join(time_clauses)


    base_sql = f"""
    SELECT impression_id, chunk_id, action, value
    FROM feedback_events
    WHERE action IN ('click','like','dwell','dislike')
    AND impression_id IS NOT NULL
    {time_clause}
    AND impression_id IN ({{}})
    """


    cur = conn.cursor(dictionary=True) if driver == "mysql.connector" else conn.cursor()

    ids = list(impression_ids)
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i:i + BATCH]
        placeholders = ",".join(["%s"] * len(batch_ids))
        sql = base_sql.format(placeholders)
        params = time_params + batch_ids
        cur.execute(sql, params)
        rows = cur.fetchall()

        if driver != "mysql.connector":
            rows = list(rows)

        for r in rows:
            imp = r.get("impression_id")
            cid = str(r.get("chunk_id") or "")
            act = r.get("action")
            val = r.get("value")
            if not imp or not cid or not act:
                continue
            update_signal((imp, cid), act, val)

    cur.close()
    return actions_map

def relevance_from_signals(sig, dwell_threshold=8.0, signal="all"):
    """
    Convert aggregated signals to a graded relevance label.
    signal:
      - all: like(2), click(1), dwell_max>=threshold(1)
      - clicklike: like(2), click(1)
      - click: click(1)
      - like: like(2)
    dislike only reduces if no positive; final label clamped to [0,2].
    """
    if not sig:
        return 0

    rel = 0

    if signal in ("all", "clicklike", "like"):
        if sig.get("like", 0) > 0:
            rel = max(rel, 2)

    if signal in ("all", "clicklike", "click"):
        if sig.get("click", 0) > 0:
            rel = max(rel, 1)

    if signal == "all":
        if float(sig.get("dwell_max", 0.0)) >= dwell_threshold:
            rel = max(rel, 1)

    if sig.get("dislike", 0) > 0 and rel == 0:
        rel = -1

    return max(0, rel)



def dcg_at_k(labels, k):
    dcg = 0.0
    for i, rel in enumerate(labels[:k], start=1):
        gain = (2 ** rel - 1)
        dcg += gain / math.log2(i + 1)
    return dcg


def ndcg_at_k(labels, k):
    dcg = dcg_at_k(labels, k)
    ideal = dcg_at_k(sorted(labels, reverse=True), k)
    if ideal <= 0:
        return 0.0
    return dcg / ideal


def mrr_at_k(labels, k):
    for i, rel in enumerate(labels[:k], start=1):
        if rel > 0:
            return 1.0 / i
    return 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Evaluate impressions within last N days (by ts)")
    parser.add_argument("--since", type=str, default="", help="Evaluate impressions with ts >= since (e.g. '2026-02-06 23:45:59'). Overrides --days if set.")
    parser.add_argument("--k", type=int, default=5, help="K for NDCG@K / MRR@K")
    parser.add_argument("--limit", type=int, default=5000, help="Max number of impression rows to scan")
    parser.add_argument("--dwell_threshold", type=float, default=8.0, help="Dwell threshold to treat as relevant")
    parser.add_argument("--policies", type=str, default="", help="Comma-separated policies to include (optional)")
    parser.add_argument("--signal", type=str, default="all", choices=["all", "clicklike", "click", "like"], help="Relevance signals to use: all|clicklike|click|like")
    parser.add_argument("--model_version", type=str, default="", help="Filter impressions by model_version")
    parser.add_argument("--only_has_pos", action="store_true", help="Only evaluate impressions that have at least one positive in topK")
    parser.add_argument("--until", type=str, default="", help="Evaluate impressions with ts < until (e.g. '2026-02-07 02:06:40').")

    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()] or None
    since = args.since.strip() or None
    model_version = args.model_version.strip() or None
    until = args.until.strip() or None



    conn, driver = get_db_conn()
    try:
        impressions = fetch_impressions(
            conn, driver,
            days=args.days,
            since=since,
            until=until,
            max_impressions=args.limit,
            policies=policies,
            model_version=model_version
        )


        if not impressions:
            print("No impressions found. Check ts, days, and policy filter.")
            return

        # group impressions by impression_id
        by_imp = defaultdict(list)
        for r in impressions:
            imp_id = r["impression_id"]
            by_imp[imp_id].append(r)

        impression_ids = set(by_imp.keys())
        actions_map = fetch_actions(
            conn, driver,
            impression_ids,
            days=args.days,
            since=since,
            until=until
        )

        # compute per-impression metrics grouped by policy
        stats = defaultdict(lambda: {"ndcg_sum": 0.0, "mrr_sum": 0.0, "n": 0, "has_pos": 0})

        for imp_id, rows in by_imp.items():
            # Each impression_id may contain mixed policy in theory; we take the first non-null
            policy = next((r.get("policy") for r in rows if r.get("policy")), "unknown")


            # sort by rank
            rows_sorted = sorted(rows, key=lambda x: int(x.get("rank_pos") or 10**9))
            labels = []
            for r in rows_sorted:
                cid = str(r.get("chunk_id") or "")
                sig = actions_map.get((imp_id, cid))
                rel = relevance_from_signals(sig, dwell_threshold=args.dwell_threshold, signal=args.signal)
                labels.append(rel)

            has_pos_in_topk = any(l > 0 for l in labels[:args.k])
            if args.only_has_pos and not has_pos_in_topk:
                continue


            nd = ndcg_at_k(labels, args.k)
            mr = mrr_at_k(labels, args.k)

            stats[policy]["ndcg_sum"] += nd
            stats[policy]["mrr_sum"] += mr
            stats[policy]["n"] += 1
            if has_pos_in_topk:
                stats[policy]["has_pos"] += 1


        # print report
        if since and until:
            time_desc = f"since={since}, until={until}"
        elif since:
            time_desc = f"since={since}"
        elif until:
            time_desc = f"until={until}"
        else:
            time_desc = f"days={args.days}"

        print(f"\nOffline Eval ({time_desc}, K={args.k}, signal={args.signal}, only_has_pos={args.only_has_pos}, impressions={sum(v['n'] for v in stats.values())})")

        print("-" * 72)
        header = f"{'policy':<16} {'impr':>6} {'pos@K%':>8} {'NDCG@K':>10} {'MRR@K':>10}"
        print(header)
        print("-" * 72)

        # stable order: rerank first
        ordered = sorted(stats.items(), key=lambda kv: (0 if "rerank" in kv[0] else 1, kv[0]))
        for policy, s in ordered:
            n = s["n"]
            ndcg = s["ndcg_sum"] / n if n else 0.0
            mrr = s["mrr_sum"] / n if n else 0.0
            if args.only_has_pos:
                pos_rate = 100.0
            else:
                pos_rate = (s["has_pos"] / n * 100.0) if n else 0.0

            print(f"{policy:<16} {n:>6} {pos_rate:>7.2f}% {ndcg:>10.4f} {mrr:>10.4f}")


        print("-" * 72)
        print("Notes:")
        print("  - Positive label: like(2), click(1), dwell_max>=threshold(1). dislike only reduces if no positive.")
        print("  - If an impression has no positive at all, NDCG/MRR become 0 for that impression.\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
