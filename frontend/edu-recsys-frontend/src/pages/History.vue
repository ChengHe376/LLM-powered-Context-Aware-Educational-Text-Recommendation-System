<template>
  <div class="grid">
    <section class="card">
      <div class="row">
        <h3>Recent Queries</h3>
        <button class="btn2" @click="history.clearAll">Clear</button>
      </div>

      <div v-if="!history.recentQueries.length" class="meta">Empty</div>
      <ul v-else class="ul">
        <li v-for="q in history.recentQueries" :key="q" class="li">{{ q }}</li>
      </ul>
    </section>

    <section class="card">
      <div class="row">
        <h3>Feedback Events (local)</h3>
        <div class="meta">count: {{ history.feedbackEvents.length }}</div>
      </div>

      <div v-if="!history.feedbackEvents.length" class="meta">Empty</div>
      <div v-else class="events">
        <div v-for="(e, i) in history.feedbackEvents" :key="i" class="evt">
          <div class="meta">
            {{ new Date(e.ts).toLocaleString() }} | {{ e.action }} | value={{ e.value }}
          </div>
          <div class="mono">chunk_id: {{ e.chunkId }}</div>
          <div class="mono">query: {{ e.queryText }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { useHistoryStore } from "../stores/history"
const history = useHistoryStore()
history.hydrate()
</script>

<style scoped>
.grid { display:grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 16px; }
.row { display:flex; align-items:center; justify-content:space-between; gap: 10px; margin-bottom: 10px; }
.btn2 { padding: 8px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; cursor:pointer; }
.meta { opacity: 0.75; font-size: 12px; }
.ul { margin: 0; padding-left: 18px; }
.li { margin: 6px 0; }
.events { display:flex; flex-direction:column; gap: 10px; }
.evt { padding: 12px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.10); background: rgba(255,255,255,0.04); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 12px; opacity: 0.9; margin-top: 4px; }
</style>
