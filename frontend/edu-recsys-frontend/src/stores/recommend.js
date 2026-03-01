import { defineStore } from "pinia"
import { api, normalizeError } from "../api/client"
import { useAuthStore } from "./auth"
import { useHistoryStore } from "./history"

export const useRecommendStore = defineStore("recommend", {
  state: () => ({
    queryText: "",
    topK: 5,
    results: [],
    contributions: [],
    loading: false,
    error: "",
    sessionId: "",
    requestId: "",
    impressionId: "",
    servedPolicy: "",
    modelVersion: null,
    latencyMs: null
  }),
  actions: {
    setQuery(text) {
      this.queryText = text || ""
    },

    ensureSession() {
      if (this.sessionId) return

      const KEY = "edu_recsys_session_v1"
      const saved = localStorage.getItem(KEY)
      if (saved) {
        this.sessionId = saved
        return
      }

      const sid = `s_${Date.now()}_${Math.random().toString(16).slice(2)}`
      this.sessionId = sid
      localStorage.setItem(KEY, sid)
    },

    async runRecommend() {
      const auth = useAuthStore()
      const history = useHistoryStore()
      this.ensureSession()

      const query = (this.queryText || "").trim()
      if (!query) {
        this.error = "Please enter a query"
        return
      }

      this.loading = true
      this.error = ""
      this.results = []
      this.contributions = []

      try {
        const res = await api.post("/recommend", {
          user_id: auth.userId,
          query_text: query,
          topk: Number(this.topK),
          session_id: this.sessionId,
          use_rerank: true,
          policy: "faiss+rerank",
          context: {}
        })

        const rows = res.data?.recommendations || []

        this.requestId = res.data?.request_id || ""
        this.impressionId = res.data?.impression_id || ""
        this.servedPolicy = res.data?.policy || ""
        this.modelVersion = res.data?.model_version ?? null
        this.latencyMs = res.data?.latency_ms ?? null

        this.results = rows.map((r, idx) => ({
          chunkId: r.Id,
          text: r.Segment,

          finalScore: Number(r.Score),
          faissScore: Number(r.FaissScore),
          rerankScore: r.RerankScore == null ? null : Number(r.RerankScore),

          rank: Number(r.Rank) || (idx + 1)
        }))


        const contrib = res.data?.rec_contributions?.faiss_retrieval
        this.contributions = Array.isArray(contrib)
          ? contrib.map((x) => Number(x))
          : this.results.map((x) => Number(x.faissScore))


      } catch (e) {
        this.error = normalizeError(e).message
      } finally {
        this.loading = false
      }
    },

    
    async sendFeedback({ chunkId, score, rank, action, value }) {
      const auth = useAuthStore()
      const history = useHistoryStore()
      const query = (this.queryText || "").trim()
      if (!auth.userId || !query || !chunkId) return

      try {
        await api.post("/feedback", {
          user_id: auth.userId,
          query_text: query,
          chunk_id: chunkId,
          score: score ?? null,
          action: action || "click",
          value: value ?? null,

          session_id: this.sessionId,
          request_id: this.requestId,
          impression_id: this.impressionId,
          policy: this.servedPolicy,
          model_version: this.modelVersion,
          latency_ms: this.latencyMs,
          rank: rank ?? null
        })

        history.pushFeedback({
          ts: Date.now(),
          userId: auth.userId,
          queryText: query,
          chunkId,
          score: score ?? null,
          action: action || "click",
          value: value ?? null
        })
      } catch {
        // 反馈失败不阻塞主流程
      }
    }
  }
})
