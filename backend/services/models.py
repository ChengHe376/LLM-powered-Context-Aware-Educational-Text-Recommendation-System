from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from sqlalchemy.dialects.mysql import JSON

from datetime import datetime
from services.db import Base

class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)

    user_id = Column(String(128), nullable=False, index=True)
    query_text = Column(Text, nullable=False)

    chunk_id = Column(String(64), nullable=False, index=True)
    score = Column(Float)

    action = Column(String(32), nullable=False, index=True)
    value = Column(Float)

    # --- impression & attribution ---
    session_id = Column(String(64), index=True)
    request_id = Column(String(64))
    impression_id = Column(String(64), index=True)

    # rank 是关键字风险，建议 Python 属性名叫 rank_pos，但列名仍然是 rank
    rank_pos = Column("rank", Integer)

    # --- policy / versioning ---
    policy = Column(String(32))
    model_version = Column(String(64))
    index_version = Column(String(64))

    # --- context / perf / bandit ---
    context_json = Column(JSON)
    latency_ms = Column(Integer)
    propensity = Column(Float)


Index("idx_user_chunk_ts", FeedbackEvent.user_id, FeedbackEvent.chunk_id, FeedbackEvent.ts)
Index("idx_feedback_session_id", FeedbackEvent.session_id)
Index("idx_feedback_impression_id", FeedbackEvent.impression_id)
