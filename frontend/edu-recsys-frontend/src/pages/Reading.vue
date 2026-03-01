<template>
  <div class="grid">
    <section class="card">
      <div class="row">
        <h3>Reading</h3>
      </div>


      <label class="label">Query (for recommend & feedback)</label>
      <textarea class="ta" v-model="rec.queryText" rows="3" placeholder="Enter keywords while reading..." />

      <div class="row" style="margin-top: 10px">
        <button class="btn2" @click="rec.runRecommend" :disabled="rec.loading">
          {{ rec.loading ? "Searching..." : "Recommend TopK" }}
        </button>
      </div>

      <div v-if="(rec.results?.length || 0) > 0" class="list" style="margin-top: 12px">
        <div v-for="r in rec.results" :key="r.chunkId" class="item">
          <div class="idx">
            #{{ r.rank }} · Final: {{ r.finalScore.toFixed(4) }}
            <span style="margin-left: 10px">FAISS: {{ r.faissScore.toFixed(4) }}</span>
            <span v-if="r.rerankScore !== null" style="margin-left: 10px">Rerank: {{ r.rerankScore.toFixed(4) }}</span>
            <span class="cid">chunk_id: {{ r.chunkId }}</span>
          </div>
          <div class="text">{{ r.text }}</div>
        </div>
      </div>


      <div v-if="streamError" class="err">{{ streamError }}</div>

      <div class="row" style="margin-top: 10px">
        <button class="btn" @click="startStream" :disabled="streamLoading">
          {{ streamLoading ? "Starting..." : "Start Reading" }}
        </button>
      </div>

      <div class="row" style="margin-top: 10px">
        <button class="btn2" @click="loadMore" :disabled="streamLoading || !nextCursor">
          {{ streamLoading ? "Loading..." : (nextCursor ? "Load More" : "No More") }}
        </button>
      </div>

      <div class="meta" style="margin-top: 10px" v-if="streamChunks.length">
        Loaded: {{ streamChunks.length }} chunks
      </div>

      <div class="meta" v-if="nextCursor?.pos != null">
        Cursor pos: {{ nextCursor.pos }}
      </div>


    </section>

    <section class="card">
      <div class="row">
        <h3>Reading Stream</h3>
        <div class="meta">
          {{ streamChunks.length ? `chunks: ${streamChunks.length}` : "not started" }}
        </div>
      </div>

      <div v-if="streamLoading && !streamChunks.length" class="meta">Loading...</div>
      <div v-else-if="!streamChunks.length" class="meta">Click “Start Reading” to load content</div>

      <div v-else class="list">
        <div v-for="c in streamChunks" :key="c.chunk_id" class="item">
          <div class="itemHead">
            <div class="idx">
              doc_id: {{ c.doc_id }} · #{{ c.order_in_doc }}
              <span class="cid">chunk_id: {{ c.chunk_id }}</span>
            </div>
            <div class="actions">
              <button class="btn3" @click="useAsQuery(c.text)">Use as query</button>
              <button class="btn3" @click="copy(c.text)">Copy</button>
              <button class="btn3" @click="like(c)">👍</button>
              <button class="btn3" @click="dislike(c)">👎</button>
            </div>
          </div>

          <div class="text">{{ c.text }}</div>
        </div>
      </div>

      <div class="pager" v-if="streamChunks.length">
        <button class="btn2" @click="loadMore" :disabled="streamLoading || !nextCursor">
          {{ streamLoading ? "Loading..." : (nextCursor ? "Load More" : "No More") }}
        </button>
      </div>
    </section>

  </div>
</template>

<script setup>
import { ref } from "vue"
import { useRouter } from "vue-router"
import { useRecommendStore } from "../stores/recommend"
import { useAuthStore } from "../stores/auth"
import { api } from "../api/client"


const router = useRouter()
const rec = useRecommendStore()
const auth = useAuthStore()
auth.hydrate()

const streamChunks = ref([])
const nextCursor = ref(null)
const streamLoading = ref(false)
const streamError = ref("")

async function startStream() {
  streamChunks.value = []
  nextCursor.value = null
  await loadMore()
}

async function loadMore() {
  if (streamLoading.value) return
  streamLoading.value = true
  streamError.value = ""
  try {
    const params = { limit: 50 }
    if (nextCursor.value?.pos != null) {
      params.pos = nextCursor.value.pos
    }
    const res = await api.get("/stream", { params })

    const chunks = res.data?.chunks || []
    streamChunks.value.push(...chunks)
    nextCursor.value = res.data?.next || null
  } catch (e) {
    streamError.value = e?.message || "Failed to load stream"
  } finally {
    streamLoading.value = false
  }
}

function like(c) {
  // 反馈必须带 query_text：用当前 rec.queryText
  rec.sendFeedback({
    chunkId: c.chunk_id,
    score: null,
    action: "like",
    value: 1
  })
}
function dislike(c) {
  rec.sendFeedback({
    chunkId: c.chunk_id,
    score: null,
    action: "dislike",
    value: -1
  })
}


function useAsQuery(text) {
  rec.setQuery(text)
  router.push("/app/recommend")
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {}
}
</script>

<style scoped>
.grid { display:grid; grid-template-columns: 320px 1fr; gap: 14px; }
.card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 16px; }
.row { display:flex; align-items:center; justify-content:space-between; gap: 10px; margin-bottom: 10px; }
.label { display:block; margin-top: 10px; margin-bottom: 6px; opacity:0.9; font-size: 13px; }
.select { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; }
.btn { width: 100%; margin-top: 12px; padding: 10px 12px; border-radius: 12px; border:0; background: rgba(99,102,241,0.85); color:white; cursor:pointer; font-weight: 600; }
.btn2 { padding: 8px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; cursor:pointer; }
.btn3 { padding: 6px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; cursor:pointer; font-size: 12px; }
.meta { opacity: 0.75; font-size: 12px; }
.err { color: #ff8a8a; margin: 8px 0; }
.list { display:flex; flex-direction:column; gap: 12px; }
.item { padding: 12px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.10); background: rgba(255,255,255,0.04); }
.itemHead { display:flex; justify-content:space-between; align-items:center; gap: 10px; margin-bottom: 8px; }
.idx { font-size: 12px; opacity: 0.8; }
.actions { display:flex; gap: 8px; }
.text { white-space: pre-wrap; line-height: 1.55; font-size: 13px; opacity: 0.95; max-height: 260px; overflow:auto; }
.pager { margin-top: 12px; display:flex; gap: 10px; justify-content:flex-end; }
.ta { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; outline:none; resize: vertical; }
.ta:focus { border-color: rgba(99,102,241,0.55); }
</style>
