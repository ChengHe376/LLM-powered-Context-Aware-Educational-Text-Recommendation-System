<template>
  <div class="card">
    <h3>Settings</h3>
    <div class="meta">API baseURL: {{ baseURL }}</div>
    <div class="meta">Tip: edit .env.development (VITE_API_BASE_URL) if needed.</div>
  </div>
</template>

<script setup>
const baseURL =
  import.meta.env.VITE_API_BASE_URL?.trim()
    ? import.meta.env.VITE_API_BASE_URL.trim()
    : "/__backend (vite proxy)"
</script>

<style scoped>
.card { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); border-radius: 18px; padding: 16px; }
.meta { opacity: 0.8; font-size: 13px; margin-top: 10px; }
</style>
