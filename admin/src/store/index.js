/**
 * 管理员后台 Pinia 状态管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// ===== 管理员认证状态 =====
export const useAdminStore = defineStore('admin', () => {
  const token = ref(localStorage.getItem('admin_token') || '')
  const adminInfo = ref(JSON.parse(localStorage.getItem('admin_info') || 'null'))
  const isLoggedIn = computed(() => !!token.value)

  function login(info) {
    token.value = 'admin_logged_in'
    adminInfo.value = info
    localStorage.setItem('admin_token', 'admin_logged_in')
    localStorage.setItem('admin_info', JSON.stringify(info))
  }

  function logout() {
    token.value = ''
    adminInfo.value = null
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_info')
  }

  return { token, adminInfo, isLoggedIn, login, logout }
})

// ===== 侧边栏状态 =====
export const useSidebarStore = defineStore('sidebar', () => {
  const isCollapsed = ref(false)

  function toggle() {
    isCollapsed.value = !isCollapsed.value
  }

  return { isCollapsed, toggle }
})