<template>
  <div class="grid">
    <section class="panel">
      <h3>Search & Recommend</h3>

      <label class="label">Query</label>
      <textarea class="ta" v-model="rec.queryText" rows="8" placeholder="Describe what you want to learn..." />

      <div class="row">
        <div class="field">
          <div class="label2">TopK</div>
          <input class="input" type="number" min="1" max="20" v-model.number="rec.topK" />
        </div>

        <button class="btn" @click="rec.runRecommend" :disabled="rec.loading">
          {{ rec.loading ? "Searching..." : "Recommend" }}
        </button>
      </div>

      <div v-if="rec.error" class="err">{{ rec.error }}</div>

      <div class="meta" v-if="rec.contributions.length">
        Scores: {{ rec.contributions.map(x => Number(x).toFixed(3)).join(", ") }}
      </div>
    </section>

    <section class="panel">
      <div class="row">
        <h3>Results</h3>
        <div class="meta">count: {{ rec.results.length }}</div>
      </div>

      <div v-if="rec.loading" class="meta">Loading...</div>
      <div v-else-if="!rec.results.length" class="meta">No results</div>

      <div v-else class="list">
        <div v-for="r in rec.results" :key="r.chunkId">
          <ResultCard
            :chunk-id="r.chunkId"
            :text="r.text"
            :rank="r.rank"
            :final-score="r.finalScore"
            :score="r.faissScore"
            :rerank-score="r.rerankScore"
            @like="like(r)"
            @dislike="dislike(r)"
            @rate="(stars) => rate(r, stars)"
          />


          <div class="rateRow">
            <span class="meta">Rate:</span>
            <button class="btn2" v-for="x in 5" :key="x" @click="rate(r, x)">{{ x }}</button>
            <button class="btn2" @click="copy(r.text)">Copy</button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import ResultCard from "../components/ResultCard.vue"
import { useRecommendStore } from "../stores/recommend"

const rec = useRecommendStore()

function like(r) {
  rec.sendFeedback({
    chunkId: r.chunkId,
    score: r.faissScore, 
    rank: r.rank,
    action: "like",
    value: 1
  })
}

function dislike(r) {
  rec.sendFeedback({
    chunkId: r.chunkId,
    score: r.faissScore, 
    rank: r.rank,
    action: "dislike",
    value: -1
  })
}

function rate(r, stars) {
  rec.sendFeedback({
    chunkId: r.chunkId,
    score: r.faissScore, 
    rank: r.rank,
    action: "rating",
    value: Number(stars)
  })
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    // 复制也作为一个轻量行为
  } catch {}
}
</script>

<style scoped>
.grid { display:grid; grid-template-columns: 360px 1fr; gap: 14px; }
.panel { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 16px; }
.label { display:block; margin-top: 8px; margin-bottom: 6px; opacity:0.9; font-size: 13px; }
.ta { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; outline:none; resize: vertical; }
.ta:focus { border-color: rgba(99,102,241,0.55); }
.row { display:flex; align-items:center; justify-content:space-between; gap: 10px; margin-top: 12px; }
.field { display:flex; flex-direction:column; gap: 6px; }
.label2 { opacity: 0.8; font-size: 12px; }
.input { width: 90px; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; }
.btn { flex: 1; padding: 10px 12px; border-radius: 12px; border:0; background: rgba(99,102,241,0.85); color:white; cursor:pointer; font-weight: 600; }
.btn:disabled { opacity: 0.6; cursor:not-allowed; }
.btn2 { padding: 7px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; cursor:pointer; font-size: 12px; }
.err { color: #ff8a8a; margin-top: 10px; }
.meta { opacity: 0.75; font-size: 12px; }
.list { display:flex; flex-direction:column; gap: 12px; margin-top: 12px; }
.rateRow { margin: 10px 0 18px; display:flex; align-items:center; gap: 8px; flex-wrap: wrap; }
</style>
