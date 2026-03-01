import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

APP_ENV = os.getenv("APP_ENV", "dev")
SECRET_KEY = os.getenv("SECRET_KEY", "change_me")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
RAW_DIR = Path(os.getenv("RAW_DIR", str(DATA_DIR / "raw"))).resolve()
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", str(DATA_DIR / "processed"))).resolve()
INDEX_DIR = Path(os.getenv("INDEX_DIR", str(BASE_DIR / "indexes"))).resolve()
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs"))).resolve()

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-small-zh-v1.5")

RERANK_MODEL_PATH = os.getenv(
    "RERANK_MODEL_PATH",
    str((BASE_DIR / "models" / "bge-reranker-v4").resolve())
)

RERANK_TOPN = int(os.getenv("RERANK_TOPN", "50"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "1") == "1"

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

def ensure_dirs():
    for p in [DATA_DIR, RAW_DIR, PROCESSED_DIR, INDEX_DIR, LOG_DIR]:
        p.mkdir(parents=True, exist_ok=True)