import axios from "axios"

const baseURL =
  import.meta.env.VITE_API_BASE_URL?.trim()
    ? import.meta.env.VITE_API_BASE_URL.trim()
    : "/__backend"

export const api = axios.create({
  baseURL,
  timeout: 20000
})

export function normalizeError(e) {
  const msg =
    e?.response?.data?.error ||
    e?.response?.data?.message ||
    e?.message ||
    "Request failed"
  const status = e?.response?.status
  return { status, message: msg, raw: e }
}
