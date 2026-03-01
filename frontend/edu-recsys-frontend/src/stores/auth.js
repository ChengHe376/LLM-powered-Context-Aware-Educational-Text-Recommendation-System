import { defineStore } from "pinia"
import { api, normalizeError } from "../api/client"

const KEY = "edu_recsys_auth_v1"

export const useAuthStore = defineStore("auth", {
  state: () => ({
    userId: "",
    loggedIn: false,
    loading: false,
    error: ""
  }),
  actions: {
    hydrate() {
      if (this.loggedIn) return
      const raw = localStorage.getItem(KEY)
      if (!raw) return
      try {
        const obj = JSON.parse(raw)
        this.userId = obj.userId || ""
        this.loggedIn = !!this.userId
      } catch {}
    },
    persist() {
      localStorage.setItem(KEY, JSON.stringify({ userId: this.userId }))
    },
    async login(username, password) {
      this.loading = true
      this.error = ""
      try {
        const res = await api.post("/login", { username, password })
        this.userId = res.data.user_id
        this.loggedIn = true
        this.persist()
        return true
      } catch (e) {
        const err = normalizeError(e)
        this.error = err.message
        this.loggedIn = false
        return false
      } finally {
        this.loading = false
      }
    },
    logout() {
      this.userId = ""
      this.loggedIn = false
      this.error = ""
      localStorage.removeItem(KEY)
    }
  }
})
