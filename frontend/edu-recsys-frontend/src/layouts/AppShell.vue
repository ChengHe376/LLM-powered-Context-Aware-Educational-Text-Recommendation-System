<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">EduText Recommender</div>
      <div class="spacer"></div>
      <div class="user">
        <span class="uid">user: {{ auth.userId }}</span>
        <button class="btn" @click="onLogout">Logout</button>
      </div>
    </header>

    <div class="body">
      <aside class="sidebar">
        <router-link class="nav" to="/app/reading">Reading</router-link>
        <router-link class="nav" to="/app/recommend">Search & Recommend</router-link>
        <router-link class="nav" to="/app/history">History</router-link>
        <router-link class="nav" to="/app/settings">Settings</router-link>
      </aside>

      <main class="main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from "../stores/auth"
import { useHistoryStore } from "../stores/history"
import { useRouter } from "vue-router"

const auth = useAuthStore()
const history = useHistoryStore()
const router = useRouter()

history.hydrate()

function onLogout() {
  auth.logout()
  router.push("/login")
}
</script>

<style scoped>
.shell { min-height: 100vh; display: flex; flex-direction: column; background: #0b1020; color: #e6e8f0; }
.topbar { height: 56px; display:flex; align-items:center; padding: 0 16px; border-bottom: 1px solid rgba(255,255,255,0.08); }
.brand { font-weight: 700; letter-spacing: 0.2px; }
.spacer { flex: 1; }
.user { display:flex; gap: 12px; align-items:center; }
.uid { opacity: 0.85; font-size: 13px; }
.btn { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.12); color: #e6e8f0; padding: 6px 10px; border-radius: 10px; cursor:pointer; }
.btn:hover { background: rgba(255,255,255,0.14); }

.body { flex: 1; display:flex; }
.sidebar { width: 220px; padding: 14px; border-right: 1px solid rgba(255,255,255,0.08); }
.nav { display:block; padding: 10px 12px; border-radius: 12px; color: #e6e8f0; text-decoration: none; margin-bottom: 8px; background: rgba(255,255,255,0.04); }
.nav.router-link-active { background: rgba(99,102,241,0.28); border: 1px solid rgba(99,102,241,0.40); }
.main { flex: 1; padding: 18px; }
</style>
