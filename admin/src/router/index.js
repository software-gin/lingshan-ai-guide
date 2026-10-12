/**
 * 管理后台路由配置
 * 严格区分管理员权限，使用Layout作为页面容器
 */
import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login'
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
      meta: { title: '管理员登录' }
    },
    {
      path: '/',
      component: () => import('@/views/Layout.vue'),
      meta: { requiresAuth: true },
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '数据大屏' }
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('@/views/UserManage.vue'),
          meta: { title: '用户管理' }
        },
        {
          path: 'digital-humans',
          name: 'digital-humans',
          component: () => import('@/views/DigitalHumanManage.vue'),
          meta: { title: '数字人管理' }
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/KnowledgeManage.vue'),
          meta: { title: '知识库管理' }
        },
        {
          path: 'routes',
          name: 'routes',
          component: () => import('@/views/RouteManage.vue'),
          meta: { title: '游览路线管理' }
        },
        {
          path: 'route-feedbacks/:id',
          name: 'route-feedbacks',
          component: () => import('@/views/RouteFeedbacks.vue'),
          meta: { title: '路线评价详情' }
        },
        {
          path: 'chat-logs',
          name: 'chat-logs',
          component: () => import('@/views/ChatLogs.vue'),
          meta: { title: '对话日志' }
        },
        {
          path: 'ai-config',
          name: 'ai-config',
          component: () => import('@/views/AIConfig.vue'),
          meta: { title: 'AI参数配置' }
        },
        {
          path: 'admins',
          name: 'admins',
          component: () => import('@/views/AdminManage.vue'),
          meta: { title: '管理员管理' }
        },
        {
          path: 'emotion-report',
          name: 'emotion-report',
          component: () => import('@/views/EmotionReport.vue'),
          meta: { title: '游客感受度报告' }
        },
        {
          path: 'consumption',
          name: 'consumption',
          component: () => import('@/views/ConsumptionAnalysis.vue'),
          meta: { title: '消费分析' }
        }
      ]
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('admin_token')
  if (to.meta.requiresAuth && !token) {
    next({ name: 'login' })
  } else {
    next()
  }
})

export default router