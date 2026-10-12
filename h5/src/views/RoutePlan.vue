<template>
  <div class="route-page">
    <van-nav-bar title="游览路线规划" left-arrow @click-left="$router.back()" />

    <!-- 顶部偏好标签栏（小红书风格可横向滚动） -->
    <div class="filter-bar">
      <div class="filter-scroll">
        <span
          v-for="tag in filterTags"
          :key="tag.value"
          :class="['filter-tag', { active: activeFilter === tag.value }]"
          @click="activeFilter = tag.value"
        >{{ tag.label }}</span>
      </div>
      <van-button size="mini" round class="pref-btn" @click="showPrefPopup = true">
        偏好 ✦
      </van-button>
    </div>

    <!-- 瀑布流卡片区域 -->
    <div class="waterfall-wrap">
      <!-- 骨架屏加载 -->
      <div v-if="loading" class="waterfall skeleton-mode">
        <div v-for="i in 6" :key="i" class="waterfall-card skeleton">
          <div class="skeleton-img" :style="{ height: imgHeights[i % imgHeights.length] }"></div>
          <div class="skeleton-body">
            <div class="skeleton-title"></div>
            <div class="skeleton-desc"></div>
            <div class="skeleton-tags"></div>
            <div class="skeleton-meta"></div>
          </div>
        </div>
      </div>

      <div v-else class="waterfall">
        <div
          v-for="route in rankedRoutes"
          :key="route.id || route.title"
          class="waterfall-card"
          :class="{ 'priority-card': route._rankScore > 40 }"
          @click="viewRouteDetail(route)"
        >
          <div class="card-cover" :style="{ height: (route._imgHeight || '220px') }">
            <img
              v-if="route.bg_image"
              :src="route.bg_image"
              :alt="route.title"
              class="cover-image"
              loading="lazy"
              @error="handleImgError"
            />
            <div v-else class="cover-fallback" :style="{ background: getFallbackGradient(route) }"></div>
            <div class="cover-overlay"></div>
            <span class="route-type-badge">{{ route.styleLabel || route.style_label || '推荐' }}</span>
            <div v-if="route._rankScore > 40" class="priority-corner">
              TOP {{ route._rankIndex + 1 }}
            </div>
          </div>

          <div class="card-body">
            <div class="card-title">{{ route.title }}</div>
            <div class="card-sub">{{ route.subtitle }} · {{ route.duration }}</div>

            <div class="card-tags">
              <span v-for="tag in route.tags.slice(0, 3)" :key="tag" class="mini-tag">
                #{{ tag }}
              </span>
            </div>

            <div class="card-footer">
              <div class="card-action">
                <span class="rating-text">推荐指数：{{ getRecommendText(route) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!loading && rankedRoutes.length > 0" class="load-more">
        <span v-if="hasMore" class="more-text" @click="loadMore">上拉加载更多路线 ↓</span>
        <span v-else class="more-end">已加载全部路线 ✿</span>
      </div>
    </div>

    <!-- 偏好设置弹窗 -->
    <van-popup v-model:show="showPrefPopup" position="bottom" round :style="{ maxHeight: '80vh' }">
      <div class="pref-popup">
        <div class="popup-header">
          <span class="popup-title">✦ 路线偏好设置</span>
          <van-icon name="cross" size="18" @click="showPrefPopup = false" />
        </div>

        <!-- AI 智能分析偏好 -->
        <div v-if="userPrefs && userPrefs.chat_count && userPrefs.chat_count > 0" class="ai-prefs">
          <div class="ai-prefs-header">
            <span class="ai-prefs-title">对话分析偏好</span>
            <span class="ai-prefs-count">基于 {{ userPrefs.chat_count }} 次对话</span>
          </div>
          <div class="ai-prefs-body">
            <div class="ai-pref-row" v-if="aiStyleLabels.length > 0">
              <span class="ai-pref-label">风格</span>
              <div class="ai-pref-tags">
                <span
                  v-for="label in aiStyleLabels"
                  :key="label"
                  class="ai-pref-tag"
                  @click="applyAiStyle(label)"
                >
                  {{ label }}
                </span>
              </div>
            </div>
            <div class="ai-pref-row" v-if="userPrefs.avg_duration">
              <span class="ai-pref-label">时长</span>
              <span class="ai-pref-value" @click="prefForm.duration = userPrefs.avg_duration">{{ userPrefs.avg_duration }}</span>
            </div>
            <div class="ai-pref-hint">用户点击标签可自主设置偏好</div>
          </div>
        </div>

        <div class="popup-body">
          <div class="form-group">
            <div class="form-label">偏好风格</div>
            <div class="style-options">
              <div
                v-for="option in styleOptions"
                :key="option.value"
                :class="['style-option', { active: prefForm.style.includes(option.value) }]"
                @click="toggleStyle(option.value)"
              >
                <span class="option-label">{{ option.label }}</span>
              </div>

            </div>
          </div>
          <div class="form-group">
            <div class="form-label">时间预算</div>
            <div class="time-options">
              <div
                v-for="option in timeOptions"
                :key="option.value"
                :class="['time-option', { active: prefForm.duration === option.value }]"
                @click="prefForm.duration = option.value"
              >
                <span class="option-label">{{ option.label }}</span>
              </div>
            </div>
          </div>
          <div class="form-group">
            <div class="form-label">游览难度</div>
            <div class="difficulty-options">
              <div
                v-for="option in difficultyOptions"
                :key="option.value"
                :class="['difficulty-option', { active: prefForm.difficulty === option.value }]"
                @click="prefForm.difficulty = option.value"
              >
                <span class="option-label">{{ option.label }}</span>
              </div>
            </div>
          </div>
          <div class="form-group">
            <div class="form-label">兴趣点</div>
            <div class="interest-options">
              <div
                v-for="option in interestOptions"
                :key="option.value"
                :class="['interest-option', { active: prefForm.interests.includes(option.value) }]"
                @click="toggleInterest(option.value)"
              >
                <span class="option-label">{{ option.label }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="popup-footer">
          <van-button round block class="pref-reset-btn" @click="resetPreferences">重置偏好</van-button>
          <van-button round block class="pref-apply-btn" @click="applyPreferences">
            ✦ 应用偏好
          </van-button>
        </div>
      </div>
    </van-popup>

    <!-- 路线详情弹窗 -->
    <van-popup v-model:show="showDetailPopup" position="bottom" round :style="{ maxHeight: '85vh' }">
      <div class="detail-popup" v-if="selectedRoute">
        <div class="detail-cover">
          <img
            v-if="selectedRoute.bg_image"
            :src="selectedRoute.bg_image"
            :alt="selectedRoute.title"
            class="detail-cover-image"
            loading="lazy"
            @error="handleImgError"
          />
          <div v-else class="detail-cover-fallback" :style="{ background: getFallbackGradient(selectedRoute) }"></div>
          <div class="detail-cover-overlay">
            <span class="detail-cover-title">{{ selectedRoute.title }}</span>
            <span class="detail-cover-sub">{{ selectedRoute.subtitle }} · {{ selectedRoute.duration }}</span>
          </div>
          <van-icon name="cross" size="20" class="detail-close" @click="showDetailPopup = false" />
        </div>

        <div class="detail-body">
          <div class="detail-meta">
            <div class="meta-item">
              <span class="meta-label">难度</span>
              <span class="meta-value">{{ selectedRoute.difficulty }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">距离</span>
              <span class="meta-value">{{ selectedRoute.distance_km }}km</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">最佳时间</span>
              <span class="meta-value">{{ selectedRoute.best_time || '全天' }}</span>
            </div>
          </div>

          <div class="detail-description">{{ selectedRoute.description }}</div>

          <div class="detail-spots">
            <div class="spots-title">途经景点</div>
            <div class="spots-list">
              <div v-for="(spot, i) in selectedRoute.spots" :key="i" class="spot-item">
                <div class="spot-index">{{ i + 1 }}</div>
                <div class="spot-content">
                  <div class="spot-name">{{ spot.name }}</div>
                  <div class="spot-desc">{{ spot.description }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-tips">{{ selectedRoute.tips }}</div>

          <div class="detail-tags">
            <van-tag v-for="tag in selectedRoute.tags" :key="tag" plain round :color="selectedRoute.color">
              # {{ tag }}
            </van-tag>
          </div>

          <div class="feedback-section">
            <div class="feedback-title">评价这条路线</div>
            <div class="rating-row">
              <van-rate
                v-model="userRating"
                size="20"
                :color="'#c8a45c'"
                :void-icon="'star-o'"
                :void-color="'#d0d0d0'"
              />
              <span class="rating-text" v-if="userRating > 0">{{ userRating }}/5</span>
            </div>
            <van-field
              v-model="feedbackComment"
              rows="2"
              type="textarea"
              placeholder="留下您的意见，帮助我们改进..."
            />
            <van-button
              class="submit-feedback-btn"
              round
              @click="submitFeedback"
              :loading="submittingFeedback"
              :disabled="userRating === 0"
            >
              {{ submittingFeedback ? '提交中...' : '提交反馈' }}
            </van-button>
          </div>
        </div>

        <div class="detail-actions">
          <van-button class="map-btn" round @click="openRouteMap(selectedRoute)">
            在地图上查看路线
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showFailToast } from 'vant'
import { getAllRoutes, getUserPreferences, submitRouteFeedback } from '@/utils/api'

const router = useRouter()

// ============ 系统主题色（CSS 变量） ============
// 与 main.js 中的 :root 变量保持一致
const THEME = {
  primary: '#5b8c5a',
  primaryLight: '#7cb342',
  gold: '#c8a45c',
  goldLight: '#e8d5a3',
  bg: '#f5f7f0',
  text: '#2e3d2e',
  textSecondary: '#6b7c6b',
  textLight: '#9aab9a'
}

// ============ 各风格路线对应的 fallback 渐变（无图片时兜底展示） ============
const FALLBACK_GRADIENTS = {
  culture:    'linear-gradient(160deg, #5b8c5a 0%, #3a6b3a 50%, #1a4a2a 100%)',
  nature:     'linear-gradient(160deg, #4caf50 0%, #2e7d32 50%, #1b5e20 100%)',
  family:     'linear-gradient(160deg, #ff9800 0%, #e65100 50%, #bf360c 100%)',
  zen:        'linear-gradient(160deg, #795548 0%, #5d4037 50%, #3e2723 100%)',
  photo:      'linear-gradient(160deg, #9c27b0 0%, #7b1fa2 50%, #4a148c 100%)',
  food:       'linear-gradient(160deg, #e91e63 0%, #c2185b 50%, #880e4f 100%)',
  architecture: 'linear-gradient(160deg, #2196f3 0%, #1565c0 50%, #0d47a1 100%)',
  history:    'linear-gradient(160deg, #607d8b 0%, #455a64 50%, #263238 100%)',
  leisure:    'linear-gradient(160deg, #009688 0%, #00796b 50%, #004d40 100%)',
  quick:      'linear-gradient(160deg, #f44336 0%, #d32f2f 50%, #b71c1c 100%)'
}

const STYLE_LABELS = {
  nature: '自然风光', culture: '佛教文化', family: '亲子游', zen: '禅意之旅',
  photo: '摄影打卡', food: '特色美食', architecture: '建筑艺术', history: '历史文化',
  leisure: '休闲漫步', quick: '速游路线'
}

// ============ 状态 ============
const loading = ref(false)
const allRoutes = ref([])

const showPrefPopup = ref(false)
const userPrefs = ref(null)
const prefForm = ref({
  style: [], duration: '', difficulty: '', interests: []
})

const showDetailPopup = ref(false)
const selectedRoute = ref(null)
const userRating = ref(0)
const feedbackComment = ref('')
const submittingFeedback = ref(false)

// 筛选标签
const activeFilter = ref('all')
const filterTags = ref([
  { label: '全部', value: 'all' },
  { label: '自然风光', value: 'nature' },
  { label: '佛教文化', value: 'culture' },
  { label: '亲子游', value: 'family' },
  { label: '禅意之旅', value: 'zen' },
  { label: '摄影打卡', value: 'photo' },
  { label: '特色美食', value: 'food' },
  { label: '建筑艺术', value: 'architecture' },
  { label: '历史文化', value: 'history' },
  { label: '休闲漫步', value: 'leisure' },
  { label: '速游路线', value: 'quick' }
])

// 瀑布流图高随机池
const imgHeights = [220, 260, 200, 280, 240, 230]
const hasMore = ref(true)

// ============ 选项定义 ============
const styleOptions = [
  { label: '文化', value: 'culture' },
  { label: '自然', value: 'nature' },
  { label: '亲子', value: 'family' },
  { label: '禅意', value: 'zen' },
  { label: '摄影', value: 'photo' },
  { label: '美食', value: 'food' },
  { label: '建筑', value: 'architecture' },
  { label: '历史', value: 'history' },
  { label: '休闲', value: 'leisure' },
  { label: '速游', value: 'quick' }
]
const timeOptions = [
  { label: '2h内', value: '2小时以内' },
  { label: '3h左右', value: '3小时左右' },
  { label: '4h左右', value: '4小时左右' },
  { label: '5h+', value: '5小时以上' }
]
const difficultyOptions = [
  { label: '低', value: '低' },
  { label: '中', value: '中' },
  { label: '高', value: '高' }
]
const interestOptions = [
  { label: '佛教文化', value: '佛教文化' },
  { label: '自然风光', value: '自然风光' },
  { label: '亲子互动', value: '亲子互动' },
  { label: '拍照打卡', value: '拍照打卡' },
  { label: '素食体验', value: '素食体验' },
  { label: '建筑艺术', value: '建筑艺术' }
]

// ============ AI 偏好标签（计算属性） ============
const aiStyleLabels = computed(() => {
  if (!userPrefs.value?.preferred_styles) return []
  return userPrefs.value.preferred_styles
    .map(s => STYLE_LABELS[s] || s)
    .filter(Boolean)
})

function applyAiStyle(label) {
  const key = Object.entries(STYLE_LABELS).find(([_, v]) => v === label)?.[0]
  if (!key) return
  if (!prefForm.value.style.includes(key)) {
    prefForm.value.style.push(key)
  }
  showSuccessToast('已采纳 AI 偏好')
}

// ============ 偏好持久化 ============
const PREFERENCES_KEY = 'lingshan_route_preferences'
function loadSavedPreferences() {
  try {
    const saved = localStorage.getItem(PREFERENCES_KEY)
    if (saved) prefForm.value = JSON.parse(saved)
  } catch { /* ignore */ }
}
function savePreferences() {
  try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(prefForm.value)) } catch { /* ignore */ }
}

// ============ 兜底封面获取（无 bg_image 时使用） ============
function getFallbackGradient(route) {
  const style = route.style || 'nature'
  return FALLBACK_GRADIENTS[style] || FALLBACK_GRADIENTS.nature
}

// ============ 图片加载失败处理 ============
function handleImgError(e) {
  console.warn('[RoutePlan] 图片加载失败:', e.target.src)
}

// ============ 展示评分（无评分则默认五星） ============
function getDisplayRating(route) {
  const rating = route.avg_rating ?? route.rating
  if (rating != null && rating > 0) {
    return rating.toFixed(1) + '★'
  }
  return '5.0★'
}

// ============ 推荐指数展示（从后端 rating 字段获取） ============
function getRecommendText(route) {
  const rating = route.rating ?? route.avg_rating
  if (rating != null && rating > 0) {
    return rating.toFixed(1) + '★'
  }
  return '5.0★'
}

// ============ 核心计算：带评分的瀑布流数据 ============
const rankedRoutes = computed(() => {
  if (allRoutes.value.length === 0) return []

  const merged = getMergedPreferences()

  // 先按 sort_order（行优先）排列，再按偏好打分排序
  const withScore = allRoutes.value
    .map(route => {
      let score = 0
      if (merged.style.length > 0) {
        if (merged.style.includes(route.style)) score += 30
        if (merged.style.some(s => route.tags?.includes(s))) score += 20
      }
      if (merged.duration) {
        const prefHours = parseDurationHours(merged.duration)
        const routeHours = parseDurationHours(route.duration)
        if (prefHours >= 0 && routeHours >= 0 && Math.abs(prefHours - routeHours) <= 1) {
          score += 25
        }
      }
      if (merged.difficulty && route.difficulty === merged.difficulty) score += 20
      if (merged.interests.length > 0) {
        const matched = merged.interests.filter(i => route.tags?.includes(i))
        score += matched.length * 15
      }
      return { ...route, _score: score }
    })

  // 始终按 sort_order 行优先排列，偏好得分作为同顺序时次级排序
  withScore.sort((a, b) => {
    const sortDiff = (a.sort_order || 0) - (b.sort_order || 0)
    if (sortDiff !== 0) return sortDiff
    return b._score - a._score
  })

  // 添加展示属性
  withScore.forEach((route, idx) => {
    route._rankIndex = idx
    route._rankScore = route._score || 0
    route.styleLabel = route.styleLabel || route.style_label || (STYLE_LABELS[route.style] || '推荐')
    route._imgHeight = imgHeights[idx % imgHeights.length] + 'px'
    route._imgError = false
  })

  // 顶部筛选过滤
  if (activeFilter.value !== 'all') {
    return withScore.filter(r => r.style === activeFilter.value)
  }
  return withScore
})

// ============ 生命周期 ============
onMounted(async () => {
  loadSavedPreferences()
  loading.value = true
  try {
    await Promise.all([loadAllRoutes(), loadUserPreferences()])
  } catch (e) {
    console.warn('[RoutePlan] 初始化失败:', e)
  } finally {
    loading.value = false
  }
})

async function loadAllRoutes() {
  try {
    const res = await getAllRoutes()
    if (res.code === 200) allRoutes.value = res.data
  } catch (e) { console.warn('[RoutePlan] 加载路线失败:', e) }
}

async function loadUserPreferences() {
  try {
    const res = await getUserPreferences()
    if (res.code === 200) userPrefs.value = res.data
  } catch (e) { console.warn('[RoutePlan] 加载偏好分析失败:', e) }
}

function getMergedPreferences() {
  const manual = prefForm.value
  const ai = userPrefs.value || {}
  return {
    style: [...new Set([...manual.style, ...(ai.preferred_styles || [])])],
    duration: manual.duration || '',
    difficulty: manual.difficulty || '',
    interests: [...new Set([...manual.interests, ...(ai.preferred_tags || [])])],
    hasAiHistory: !!ai.chat_count && ai.chat_count > 0,
    hasManualPrefs: manual.style.length > 0 || manual.duration || manual.difficulty || manual.interests.length > 0
  }
}

function parseDurationHours(str) {
  if (!str || typeof str !== 'string') return -1
  const match = str.match(/(\d+(?:\.\d+)?)[\u4e00-\u9fff]*小时/)
  return match ? parseFloat(match[1]) : -1
}

// ============ 操作函数 ============
function toggleStyle(value) {
  const idx = prefForm.value.style.indexOf(value)
  if (idx >= 0) prefForm.value.style.splice(idx, 1)
  else prefForm.value.style.push(value)
}

function toggleInterest(value) {
  const idx = prefForm.value.interests.indexOf(value)
  if (idx >= 0) prefForm.value.interests.splice(idx, 1)
  else prefForm.value.interests.push(value)
}

function resetPreferences() {
  prefForm.value = { style: [], duration: '', difficulty: '', interests: [] }
  savePreferences()
  showPrefPopup.value = false
}

async function applyPreferences() {
  savePreferences()
  showPrefPopup.value = false
  loading.value = true
  try {
    await loadUserPreferences()
    showSuccessToast('偏好已应用，路线重新推荐中...')
  } catch {
    showSuccessToast('偏好已保存')
  } finally {
    loading.value = false
  }
}

function viewRouteDetail(route) {
  selectedRoute.value = { ...route }
  userRating.value = 0
  feedbackComment.value = ''
  showDetailPopup.value = true
}

function openRouteMap(route) {
  if (!route?.spots?.length || route.spots.length < 2) return
  const spots = route.spots
  const origin = spots[0].name
  const destination = spots[spots.length - 1].name
  const waypoints = spots.length > 2 ? spots.slice(1, -1).map(s => s.name) : []
  router.push({
    path: '/route-map',
    query: { origin, destination, waypoints: waypoints.join(','), mode: 'walk' },
    state: {
      spots: spots.map(s => ({ name: s.name, description: s.description || '', latitude: s.latitude, longitude: s.longitude })),
      summary: route.description || '',
      tips: route.tips || '',
      routeName: route.title || '',
      duration: route.duration || ''
    }
  })
}

async function submitFeedback() {
  if (userRating.value === 0 || !selectedRoute.value) return
  submittingFeedback.value = true
  try {
    await submitRouteFeedback({
      routeId: selectedRoute.value.id,
      rating: userRating.value,
      comment: feedbackComment.value
    })
    showSuccessToast('感谢您的反馈！')
    showDetailPopup.value = false
  } catch (e) {
    console.warn('[RoutePlan] 提交反馈失败:', e)
    showFailToast('提交失败，请稍后重试')
  } finally {
    submittingFeedback.value = false
  }
}

function loadMore() { /* 一次性加载全部 */ }
</script>

<style scoped>
/* ========== CSS 变量（与 main.js :root 一致） ========== */
.route-page {
  --rp-primary: #5b8c5a;
  --rp-primary-light: #7cb342;
  --rp-gold: #c8a45c;
  --rp-gold-light: #e8d5a3;
  --rp-bg: #f5f7f0;
  --rp-text: #2e3d2e;
  --rp-text-secondary: #6b7c6b;
  --rp-text-light: #9aab9a;
  --rp-light-bg: #edf6ea;
  --rp-card-bg: #faf5f0;

  min-height: 100vh;
  background: var(--rp-bg);
  padding-bottom: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
}

/* ========== 顶部筛选栏 ========== */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px 8px;
  background: #fff;
  position: sticky;
  top: 46px;
  z-index: 10;
  box-shadow: 0 1px 6px rgba(91, 140, 90, 0.08);
}

.filter-scroll {
  flex: 1;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  padding: 2px 4px 6px;
}
.filter-scroll::-webkit-scrollbar { display: none; }

.filter-tag {
  flex-shrink: 0;
  font-size: 13px;
  padding: 5px 14px;
  border-radius: 16px;
  background: var(--rp-light-bg);
  color: var(--rp-text-secondary);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
  border: 1.5px solid transparent;
}

.filter-tag.active {
  background: linear-gradient(135deg, var(--rp-primary), var(--rp-primary-light));
  color: #fff;
  box-shadow: 0 3px 10px rgba(91, 140, 90, 0.3);
  font-weight: 500;
}

.pref-btn {
  flex-shrink: 0;
  color: var(--rp-primary);
  border-color: var(--rp-primary);
  font-size: 12px;
}

/* ========== 瀑布流（CSS Columns 真瀑布流，无空白） ========== */
.waterfall-wrap { padding: 10px 10px 0; }

.waterfall {
  column-count: 2;
  column-gap: 10px;
  padding: 4px;
}

.waterfall-card {
  break-inside: avoid;
  margin-bottom: 10px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(91, 140, 90, 0.08);
  cursor: pointer;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s;
  animation: card-fade-in 0.5s ease-out both;
}
.waterfall-card:nth-child(1) { animation-delay: 0.05s; }
.waterfall-card:nth-child(2) { animation-delay: 0.1s; }
.waterfall-card:nth-child(3) { animation-delay: 0.15s; }
.waterfall-card:nth-child(4) { animation-delay: 0.2s; }
.waterfall-card:nth-child(5) { animation-delay: 0.25s; }
.waterfall-card:nth-child(6) { animation-delay: 0.3s; }
.waterfall-card:nth-child(7) { animation-delay: 0.35s; }
.waterfall-card:nth-child(8) { animation-delay: 0.4s; }

@keyframes card-fade-in {
  from { opacity: 0; transform: translateY(16px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.waterfall-card:active {
  transform: scale(0.97);
  box-shadow: 0 4px 20px rgba(91, 140, 90, 0.18);
}

.waterfall-card.priority-card {
  box-shadow: 0 4px 20px rgba(200, 164, 92, 0.25);
  border: 2px solid var(--rp-gold-light);
}

/* 卡片封面（图片展示） */
.card-cover {
  position: relative;
  width: 100%;
  overflow: hidden;
}

.cover-image,
.cover-fallback {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
  display: block;
}

.cover-fallback {
  z-index: 0;
}

.cover-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(180deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0) 35%, rgba(0,0,0,0.5) 100%);
  pointer-events: none;
  z-index: 2;
}

.route-type-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  font-size: 11px;
  color: #fff;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(8px);
  padding: 4px 10px;
  border-radius: 12px;
  letter-spacing: 0.3px;
  z-index: 3;
}

.priority-corner {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--rp-gold), #a07d2a);
  padding: 4px 8px;
  border-radius: 10px;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 8px rgba(200, 164, 92, 0.5);
  z-index: 3;
}

/* 卡片正文 */
.card-body { padding: 10px 12px; }

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--rp-text);
  line-height: 1.4;
  margin-bottom: 3px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  letter-spacing: 0.2px;
}

.card-sub {
  font-size: 11px;
  color: var(--rp-text-light);
  margin-bottom: 6px;
}

.card-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.mini-tag {
  font-size: 10px;
  color: var(--rp-primary);
  background: var(--rp-light-bg);
  padding: 2px 6px;
  border-radius: 8px;
  letter-spacing: 0.2px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 6px;
  border-top: 1px solid var(--rp-light-bg);
}

.meta-dot {
  font-size: 11px;
  color: var(--rp-text-light);
}

.card-action {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--rp-primary);
}

.rating-text { font-size: 11px; color: var(--rp-gold); font-weight: 500; }

/* ========== 骨架屏 ========== */
.waterfall.skeleton-mode {
  column-count: 2;
  column-gap: 10px;
  padding: 4px;
}

.waterfall-card.skeleton {
  break-inside: avoid;
  margin-bottom: 10px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  cursor: default;
}

.skeleton-img {
  width: 100%;
  background: linear-gradient(110deg, #e8ede8 25%, #f0f4f0 50%, #e8ede8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-body { padding: 10px 12px; }

.skeleton-title,
.skeleton-desc,
.skeleton-tags,
.skeleton-meta {
  height: 12px;
  background: linear-gradient(110deg, #e8ede8 25%, #f0f4f0 50%, #e8ede8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 6px;
  margin-bottom: 6px;
}

.skeleton-title { height: 14px; width: 80%; }
.skeleton-desc { height: 10px; width: 90%; }
.skeleton-tags { height: 10px; width: 50%; }
.skeleton-meta { height: 10px; width: 40%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ========== 加载更多 ========== */
.load-more {
  text-align: center;
  padding: 20px 0 10px;
  font-size: 13px;
  color: var(--rp-gold);
}

.more-text {
  cursor: pointer;
  animation: bounce 2s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

.more-end { color: var(--rp-text-light); letter-spacing: 0.5px; }

/* ========== 偏好弹窗 ========== */
.pref-popup { padding: 20px; }

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px 16px;
  border-bottom: 1px solid var(--rp-light-bg);
  margin-bottom: 16px;
}

.popup-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--rp-text);
  letter-spacing: 0.3px;
}

/* ========== AI 智能分析偏好 ========== */
.ai-prefs {
  margin: 0 4px 16px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #edf6ea, #e8f0e6);
  border-radius: 12px;
  border: 1px solid #d0e4d0;
}

.ai-prefs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.ai-prefs-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--rp-primary);
}

.ai-prefs-count {
  font-size: 11px;
  color: var(--rp-text-light);
  background: var(--rp-light-bg);
  padding: 2px 8px;
  border-radius: 10px;
}

.ai-prefs-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-pref-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ai-pref-label {
  font-size: 12px;
  color: var(--rp-text-secondary);
  flex-shrink: 0;
  min-width: 30px;
}

.ai-pref-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.ai-pref-tag {
  font-size: 12px;
  color: var(--rp-primary);
  background: #fff;
  padding: 4px 10px;
  border-radius: 12px;
  cursor: pointer;
  border: 1px solid var(--rp-primary-light);
  transition: all 0.2s;
  user-select: none;
}

.ai-pref-tag:active {
  background: var(--rp-primary);
  color: #fff;
}

.ai-pref-value {
  font-size: 13px;
  color: var(--rp-primary);
  font-weight: 500;
  cursor: pointer;
  background: #fff;
  padding: 3px 10px;
  border-radius: 10px;
  border: 1px solid var(--rp-primary-light);
}

.ai-pref-hint {
  font-size: 11px;
  color: var(--rp-text-light);
  margin-top: 2px;
  letter-spacing: 0.2px;
}

.popup-body {
  overflow-y: auto;
  max-height: 50vh;
  -webkit-overflow-scrolling: touch;
}

.form-group { margin-bottom: 20px; }

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--rp-text-secondary);
  margin-bottom: 12px;
  padding-left: 4px;
  letter-spacing: 0.3px;
}

.style-options,
.time-options,
.difficulty-options,
.interest-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.style-option,
.time-option,
.difficulty-option,
.interest-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 12px 8px;
  border-radius: 12px;
  background: var(--rp-light-bg);
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.style-option.active,
.time-option.active,
.difficulty-option.active,
.interest-option.active {
  background: #d4edda;
  border-color: var(--rp-primary);
}

.option-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--rp-text);
  letter-spacing: 0.3px;
}

.popup-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--rp-light-bg);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pref-reset-btn {
  color: var(--rp-text-light);
  border-color: var(--rp-light-bg);
}

.pref-apply-btn {
  background: linear-gradient(135deg, var(--rp-primary), var(--rp-primary-light));
  color: #fff;
  border: none;
  box-shadow: 0 3px 12px rgba(91, 140, 90, 0.3);
}

/* ========== 详情弹窗 ========== */
.detail-popup { padding: 0 0 20px; }

.detail-cover {
  position: relative;
  width: 100%;
  height: 220px;
  overflow: hidden;
}

.detail-cover-image,
.detail-cover-fallback {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
  display: block;
}

.detail-cover-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 20px;
  background: linear-gradient(180deg, rgba(0,0,0,0) 30%, rgba(0,0,0,0.7) 100%);
  color: #fff;
  z-index: 2;
}

.detail-cover-title {
  display: block;
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 3px;
  letter-spacing: 0.3px;
}

.detail-cover-sub {
  display: block;
  font-size: 12px;
  opacity: 0.9;
  letter-spacing: 0.3px;
}

.detail-close {
  position: absolute;
  top: 12px;
  right: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.4);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  backdrop-filter: blur(8px);
}

.detail-body { padding: 16px 20px; }

.detail-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--rp-light-bg);
  border-radius: 12px;
}

.meta-item { text-align: center; flex: 1; }

.meta-label {
  font-size: 11px;
  color: var(--rp-text-light);
  margin-bottom: 3px;
  letter-spacing: 0.3px;
}

.meta-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--rp-primary);
  letter-spacing: 0.3px;
}

.detail-description {
  font-size: 13px;
  color: var(--rp-text);
  line-height: 1.7;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: #fff8e1;
  border-radius: 10px;
  letter-spacing: 0.2px;
}

.spots-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--rp-text);
  margin-bottom: 12px;
  letter-spacing: 0.3px;
}

.spots-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.spot-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.spot-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--rp-primary), var(--rp-primary-light));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(91, 140, 90, 0.3);
}

.spot-content { flex: 1; }

.spot-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--rp-text);
  margin-bottom: 2px;
  letter-spacing: 0.3px;
}

.spot-desc {
  font-size: 12px;
  color: var(--rp-text-light);
  line-height: 1.5;
  letter-spacing: 0.2px;
}

.detail-tips {
  font-size: 13px;
  color: #8a6d2e;
  background: #fff8e1;
  padding: 10px 14px;
  border-radius: 8px;
  line-height: 1.5;
  margin-bottom: 16px;
  letter-spacing: 0.2px;
}

.detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.feedback-section {
  background: var(--rp-light-bg);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.feedback-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--rp-text-secondary);
  margin-bottom: 10px;
  letter-spacing: 0.3px;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.rating-text {
  font-size: 13px;
  color: var(--rp-gold);
  font-weight: 600;
}

.submit-feedback-btn {
  background: linear-gradient(135deg, var(--rp-primary), var(--rp-primary-light));
  color: #fff;
  border: none;
  box-shadow: 0 3px 10px rgba(91, 140, 90, 0.25);
  width: 100%;
  height: 40px;
  border-radius: 20px;
}

.detail-actions { padding: 0 20px 8px; }

.map-btn {
  background: linear-gradient(135deg, var(--rp-primary), var(--rp-primary-light));
  color: #fff;
  border: none;
  font-size: 15px;
  width: 100%;
  height: 46px;
  border-radius: 23px;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 12px rgba(91, 140, 90, 0.3);
}

/* ========== 响应式适配 ========== */
@media (min-width: 414px) {
  .waterfall { column-count: 2; column-gap: 12px; }
  .card-title { font-size: 15px; }
}

@media (max-width: 350px) {
  .waterfall { column-gap: 8px; padding: 2px; }
  .waterfall-card { margin-bottom: 8px; }
  .card-body { padding: 8px 10px; }
  .card-title { font-size: 13px; }
  .card-sub { font-size: 10px; }
}

@media (orientation: landscape) {
  .waterfall { column-count: 3; }
  .detail-cover { height: 160px; }
}
</style>
