import { defineStore } from "pinia"

const KEY = "edu_recsys_history_v1"

export const useHistoryStore = defineStore("history", {
  state: () => ({
    recentQueries: [],
    feedbackEvents: []
  }),
  actions: {
    hydrate() {
      const raw = localStorage.getItem(KEY)
      if (!raw) return
      try {
        const obj = JSON.parse(raw)
        this.recentQueries = obj.recentQueries || []
        this.feedbackEvents = obj.feedbackEvents || []
      } catch {}
    },
    persist() {
      localStorage.setItem(
        KEY,
        JSON.stringify({
          recentQueries: this.recentQueries.slice(0, 50),
          feedbackEvents: this.feedbackEvents.slice(0, 200)
        })
      )
    },
    pushQuery(q) {
      const x = (q || "").trim()
      if (!x) return
      this.recentQueries = [x, ...this.recentQueries.filter((t) => t !== x)].slice(0, 50)
      this.persist()
    },
    pushFeedback(evt) {
      this.feedbackEvents = [evt, ...this.feedbackEvents].slice(0, 200)
      this.persist()
    },
    clearAll() {
      this.recentQueries = []
      this.feedbackEvents = []
      localStorage.removeItem(KEY)
    }
  }
})
