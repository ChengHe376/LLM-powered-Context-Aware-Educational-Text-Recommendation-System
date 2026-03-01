<template>
  <div class="wrap">
    <div class="card">
      <h2>Login</h2>

      <label class="label">Username</label>
      <input class="input" v-model="username" placeholder="user1" />

      <label class="label">Password</label>
      <input class="input" v-model="password" type="password" placeholder="pass1" />

      <button class="btn" :disabled="auth.loading" @click="doLogin">
        {{ auth.loading ? "Logging in..." : "Login" }}
      </button>

      <p v-if="auth.error" class="err">{{ auth.error }}</p>

      <div class="hint">
        Demo users: user1/pass1, user2/pass2 ...
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { useAuthStore } from "../stores/auth"
import { useRouter } from "vue-router"

const auth = useAuthStore()
const router = useRouter()

const username = ref("user1")
const password = ref("pass1")

async function doLogin() {
  const ok = await auth.login(username.value, password.value)
  if (ok) router.push("/app/recommend")
}
</script>

<style scoped>
.wrap { min-height: 100vh; display:flex; align-items:center; justify-content:center; background:#0b1020; color:#e6e8f0; }
.card { width: 360px; padding: 22px; border-radius: 18px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); }
.label { display:block; margin-top: 12px; margin-bottom: 6px; opacity: 0.9; font-size: 13px; }
.input { width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color:#e6e8f0; outline:none; }
.input:focus { border-color: rgba(99,102,241,0.55); }
.btn { width:100%; margin-top: 16px; padding: 10px 12px; border-radius: 12px; border: 0; background: rgba(99,102,241,0.85); color:white; cursor:pointer; font-weight: 600; }
.btn:disabled { opacity: 0.6; cursor:not-allowed; }
.err { margin-top: 12px; color: #ff8a8a; }
.hint { margin-top: 14px; font-size: 12px; opacity: 0.75; }
</style>
