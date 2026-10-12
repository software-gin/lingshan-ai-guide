/**
 * 游客移动端H5路由配置
 * 严格区分游客/管理员权限，路由鉴权隔离
 */
import { createRouter, createWebHashHistory } from 'vue-router'

// 路由守卫 - 检查登录状态
const checkAuth = (to, from, next) => {
  const token = localStorage.getItem('user_token')
  if (to.meta.requiresAuth && !token) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
}

const routes = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册' }
  },
  {
    path: '/home',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: 'AI导游', requiresAuth: true }
  },
  {
    path: '/route-plan',
    name: 'route-plan',
    component: () => import('@/views/RoutePlan.vue'),
    meta: { title: '路线规划', requiresAuth: true }
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/History.vue'),
    meta: { title: '对话历史', requiresAuth: true }
  },
  {
    path: '/user',
    name: 'user',
    component: () => import('@/views/User.vue'),
    meta: { title: '个人中心', requiresAuth: true }
  },
  {
    path: '/digital-human',
    name: 'digital-human',
    component: () => import('@/views/DigitalHuman.vue'),
    meta: { title: '切换数字人', requiresAuth: true }
  },
  {
    path: '/route-map',
    name: 'route-map',
    component: () => import('@/views/RouteMap.vue'),
    meta: { title: '路线地图', requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 全局路由守卫
router.beforeEach(checkAuth)

export default router