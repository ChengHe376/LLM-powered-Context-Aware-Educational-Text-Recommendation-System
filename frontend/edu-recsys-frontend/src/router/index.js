import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "../stores/auth"

import Login from "../pages/Login.vue"
import AppShell from "../layouts/AppShell.vue"
import Reading from "../pages/Reading.vue"
import Recommend from "../pages/Recommend.vue"
import History from "../pages/History.vue"
import Settings from "../pages/Settings.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/app/recommend" },
    { path: "/login", component: Login },
    {
      path: "/app",
      component: AppShell,
      children: [
        { path: "reading", component: Reading },
        { path: "recommend", component: Recommend },
        { path: "history", component: History },
        { path: "settings", component: Settings }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.hydrate()

  if (to.path.startsWith("/app") && !auth.loggedIn) {
    return "/login"
  }
  if (to.path === "/login" && auth.loggedIn) {
    return "/app/recommend"
  }
})

export default router
