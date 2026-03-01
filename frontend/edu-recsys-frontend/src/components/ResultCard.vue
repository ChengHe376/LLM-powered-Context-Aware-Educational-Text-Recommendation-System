<template>
  <div class="card">
    <div class="head">
      <div class="left">
        <div class="title">
          <span class="rank">#{{ rank }}</span>
          <span class="final">Final: {{ finalScore.toFixed(4) }}</span>
        </div>

        <div class="meta">
          <span class="ref">Score(ref): {{ score.toFixed(4) }}</span>
          <span v-if="rerankScore !== null" class="rerank">Rerank: {{ rerankScore.toFixed(4) }}</span>
        </div>

        <div class="cid">chunk_id: {{ chunkId }}</div>
      </div>

      <div class="right">
        <button class="btn2" @click="$emit('like')">👍 Useful</button>
        <button class="btn2" @click="$emit('dislike')">👎 Not</button>
        <select class="select" v-model.number="rating" @change="onRate">
          <option :value="0">Rate</option>
          <option v-for="x in 5" :key="x" :value="x">{{ x }}</option>
        </select>
        <button class="btn2" @click="toggle">{{ expanded ? "Collapse" : "Expand" }}</button>
      </div>
    </div>

    <div class="text" :class="{ clamp: !expanded }">{{ text }}</div>
  </div>
</template>


<script setup>
import { ref } from "vue"

const emit = defineEmits(["like", "dislike", "rate", "toggle"])

const props = defineProps({
  chunkId: { type: String, required: true },
  text: { type: String, required: true },

  rank: { type: Number, required: true },
  finalScore: { type: Number, required: true },

  // 参考分（建议传 faissScore）
  score: { type: Number, required: true },

  // rerank 分可能为空
  rerankScore: { type: Number, default: null }
})

const expanded = ref(false)
const rating = ref(0)

function toggle() {
  expanded.value = !expanded.value
  emit("toggle", expanded.value)
}

function onRate() {
  if (rating.value > 0) {
    emit("rate", rating.value)
    rating.value = 0
  }
}
</script>


<style scoped>
.card { padding: 14px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.10); background: rgba(255,255,255,0.04); }
.head { display:flex; justify-content:space-between; gap: 12px; margin-bottom: 10px; align-items:flex-start; }
.score { font-weight: 700; }
.cid { font-size: 12px; opacity: 0.75; margin-top: 2px; }
.right { display:flex; gap: 8px; flex-wrap: wrap; justify-content:flex-end; }
.btn2 { padding: 7px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; cursor:pointer; font-size: 12px; }
.select { padding: 7px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; font-size: 12px; }
.text { white-space: pre-wrap; line-height: 1.6; font-size: 13px; opacity: 0.95; }
.clamp { display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }
.title { display:flex; gap: 10px; align-items: baseline; flex-wrap: wrap }
.rank { font-weight: 800 }
.final { font-weight: 700 }
.meta { display:flex; gap: 10px; flex-wrap: wrap; font-size: 12px; opacity: 0.85; margin-top: 2px }
.ref { opacity: 0.9 }
.rerank { opacity: 0.95 }

</style>
