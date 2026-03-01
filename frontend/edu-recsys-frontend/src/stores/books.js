import { defineStore } from "pinia"
import { api, normalizeError } from "../api/client"

export const useBooksStore = defineStore("books", {
  state: () => ({
    books: [],
    selectedBook: "",
    chunks: [],
    loadingBooks: false,
    loadingContent: false,
    error: "",
    nextStart: 0,
    hasMore: false,
    total: 0
  }),
  actions: {
    async fetchBooks() {
      this.loadingBooks = true
      this.error = ""
      try {
        const res = await api.get("/docs")
        // docs: [{doc_id,title,chunks_count,source,preview}]
        this.books = res.data.docs || []

        if (!this.selectedBook && this.books.length) {
          this.selectedBook = String(this.books[0].doc_id)
        }
      } catch (e) {
        this.error = normalizeError(e).message
      } finally {
        this.loadingBooks = false
      }
    },

    async fetchBookContent(docId, { start = 0, limit = 200 } = {}) {
      this.loadingContent = true
      this.error = ""

      if (start === 0) this.chunks = []

      try {
        const res = await api.get("/doc_content", {
          params: { doc_id: String(docId), start, limit }
        })

        this.selectedBook = res.data.doc_id

        const newChunks = res.data.chunks || []
        if (start === 0) {
          this.chunks = newChunks
        } else {
          this.chunks = this.chunks.concat(newChunks)
        }

        // 可选：把分页状态也存起来，Reading.vue 用起来更方便
        this.nextStart = res.data.next_start
        this.hasMore = res.data.has_more
        this.total = res.data.total
      } catch (e) {
        this.error = normalizeError(e).message
      } finally {
        this.loadingContent = false
      }
    }

  }
})
