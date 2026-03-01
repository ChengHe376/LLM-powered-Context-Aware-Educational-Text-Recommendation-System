# 📘 LLM-Powered Context-Aware Educational Text Recommendation System

An end-to-end two-stage recommendation system for educational text
retrieval and reranking.

This project demonstrates a complete ML system lifecycle:

-   🔍 FAISS semantic retrieval (dense recall)
-   🧠 Transformer-based Cross-Encoder reranker (BGE v4)
-   📊 Offline evaluation (pos@K / NDCG@K / MRR@K)
-   🔁 Feedback simulation & Learning-to-Rank training
-   🌐 Vue + Flask full-stack demo
-   🔐 Production-grade authentication & security design

------------------------------------------------------------------------

# 🏗️ System Architecture

User Query\
↓\
FAISS Dense Retrieval (Top-N Recall)\
↓\
BGE Cross-Encoder Reranker (v4)\
↓\
Top-K Results\
↓\
User Feedback Logging\
↓\
Offline Evaluation & Retraining

------------------------------------------------------------------------

# 📂 Project Structure

backend/ experiments/ analysis/ \# Offline evaluation dataset/ \# LTR
dataset export simulation/ \# Persona-based feedback simulation
training/ \# Reranker training retrieval/ \# FAISS retriever services/
\# Rerank logic scripts/ \# Data preprocessing & index building

frontend/ edu-recsys-frontend/ public/ src/

------------------------------------------------------------------------

# 🚀 Reproducibility Guide

## Backend Setup

Create `.env`:

APP_ENV=dev\
SECRET_KEY=change_me\
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/recsys?charset=utf8mb4\
RERANK_ENABLED=1\
RERANK_TOPN=50

------------------------------------------------------------------------

## Frontend Setup

cd frontend/edu-recsys-frontend\
npm install

Create `.env.development`:

VITE_API_BASE_URL=http://localhost:5000

Run frontend:

npm run dev

------------------------------------------------------------------------

# 📦 Data Preparation

python scripts/download_dataset.py\
python scripts/build_chunks.py\
python scripts/build_faiss_index.py

------------------------------------------------------------------------

# 🔁 Feedback Simulation

python experiments/simulation/simulate_feedback_personas_v4.py

------------------------------------------------------------------------

# 🧠 Train Reranker (v4)

python experiments/training/train_reranker_v4.py

------------------------------------------------------------------------

# 📊 Offline Evaluation

python experiments/analysis/evaluate_rerank_offline.py\
--since "2026-02-06 23:45:59"\
--until "2026-02-07 02:06:40"\
--k 5\
--policies "faiss-only,faiss+rerank"

Metrics: - pos@K - NDCG@K - MRR@K

------------------------------------------------------------------------

# 📈 Experimental Results

  Version               pos@5    NDCG@5   MRR@5
  --------------------- -------- -------- --------
  FAISS only            58.65%   0.4600   0.4179
  v4 (FAISS + Rerank)   63.59%   0.4695   0.4149

v4 improves overall positive coverage under realistic traffic
distribution and was selected for deployment.

------------------------------------------------------------------------

# 🛠 Tech Stack

Backend: - Python - Flask - FAISS - SentenceTransformers - MySQL - Redis

Frontend: - Vue 3 - Vite - Axios

------------------------------------------------------------------------
