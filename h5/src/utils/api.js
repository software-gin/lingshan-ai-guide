/**
 * API请求工具
 * 封装axios，统一处理请求/响应拦截
 */
import axios from 'axios'
import { showFailToast } from 'vant'

// 创建axios实例
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  },
  withCredentials: true  // 允许跨域携带cookie
})

// 响应拦截器
api.interceptors.response.use(
  response => {
    const res = response.data
    if (res.code === 401) {
      // 未登录，跳转到登录页
      localStorage.removeItem('user_token')
      localStorage.removeItem('user_info')
      window.location.hash = '#/login'
      return Promise.reject(new Error(res.message || '未登录'))
    }
    return res
  },
  error => {
    console.error('API请求错误:', error)
    showFailToast(error?.response?.data?.message || '网络请求失败，请检查网络连接')
    return Promise.reject(error)
  }
)

// ======================== 游客接口 ========================

/** 注册 */
export const userRegister = (data) => api.post('/user/register', data)

/** 登录 */
export const userLogin = (data) => api.post('/user/login', data)

/** 退出登录 */
export const userLogout = () => api.post('/user/logout')

/** 获取用户信息 */
export const getUserInfo = () => api.get('/user/info')

/** 保存用户选中的数字人 */
export const saveUserDigitalHuman = (digitalHumanId) => api.put('/user/digital-human', { digital_human_id: digitalHumanId })

/** 获取可用数字人列表 */
export const getDigitalHumans = () => api.get('/user/digital-humans')

/** 获取路线规划（旧版，保留兼容） */
export const getRoutePlan = (type = 'all') => api.get('/user/route-plan', { params: { type } })

/** 获取全部路线列表 */
export const getAllRoutes = () => api.get('/user/route-plan/all')

/** 获取单条路线详情 */
export const getRouteDetail = (id) => api.get(`/user/route-plan/${id}`)

/** 按标签筛选路线 */
export const getRoutesByTags = (tags) => api.get('/user/route-plan/tags', { params: { tags: tags.join(',') } })

/** 获取AI推荐路线（大模型分析） */
export const getRouteRecommendation = (preferences) => api.post('/user/route-recommend', { preferences })

/** 获取用户偏好分析 */
export const getUserPreferences = () => api.get('/user/route-plan/preferences')

/** 提交路线反馈 */
export const submitRouteFeedback = (data) => api.post('/user/route-plan/feedback', data)

/** 获取用户历史反馈 */
export const getUserFeedbacks = () => api.get('/user/route-plan/feedbacks')

/** 获取对话历史 */
export const getChatHistory = (params) => api.get('/user/chat-history', { params })

/** 清除对话历史 */
export const clearChatHistory = () => api.delete('/user/chat-history')

/** 获取WebSocket连接信息 */
export const getWsInfo = () => api.get('/user/ws-info')

/** 上传图片 */
export const uploadImage = (formData) => api.post('/user/upload-image', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 60000  // 图片上传超时 60s
})

/** 上传视频（多模态视频理解，单文件 ≤128MB） */
export const uploadVideo = (formData) => api.post('/user/upload-video', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 180000  // 视频较大，超时 180s
})

/** 查看当前用户的全部长期记忆（合规：知情权） */
export const getUserMemories = () => api.get('/user/memory')

/** 一键清除当前用户的全部长期记忆（合规：被遗忘权） */
export const clearUserMemories = () => api.delete('/user/memory')

// ======================== 管理员接口 ========================

/** 管理员登录 */
export const adminLogin = (data) => api.post('/admin/login', data)

/** 管理员信息 */
export const getAdminInfo = () => api.get('/admin/info')

/** 获取用户列表 */
export const getUsers = (params) => api.get('/admin/users', { params })

/** 删除用户 */
export const deleteUser = (id) => api.delete(`/admin/users/${id}`)

/** 获取数字人列表(管理) */
export const getAdminDigitalHumans = () => api.get('/admin/digital-humans')

/** 创建数字人 */
export const createDigitalHuman = (data) => api.post('/admin/digital-humans', data)

/** 更新数字人 */
export const updateDigitalHuman = (id, data) => api.put(`/admin/digital-humans/${id}`, data)

/** 删除数字人 */
export const deleteDigitalHuman = (id) => api.delete(`/admin/digital-humans/${id}`)

/** 获取知识库列表 */
export const getKnowledgeList = (params) => api.get('/admin/knowledge', { params })

/** 创建知识条目 */
export const createKnowledge = (data) => api.post('/admin/knowledge', data)

/** 更新知识条目 */
export const updateKnowledge = (id, data) => api.put(`/admin/knowledge/${id}`, data)

/** 删除知识条目 */
export const deleteKnowledge = (id) => api.delete(`/admin/knowledge/${id}`)

/** 同步向量库 */
export const syncKnowledge = () => api.post('/admin/knowledge/sync')

/** 获取对话日志 */
export const getChatLogs = (params) => api.get('/admin/chat-logs', { params })

/** 获取数据大屏统计 */
export const getDashboardStats = () => api.get('/admin/dashboard/stats')

/** 获取AI配置 */
export const getAiConfig = () => api.get('/admin/ai-config')

/** 更新AI配置 */
export const updateAiConfig = (data) => api.put('/admin/ai-config', data)

export default api