<template>
  <div class="route-feedbacks">
    <div class="page-header">
      <el-button text @click="goBack" class="back-btn">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2 class="page-title">路线评价 - {{ routeName }}</h2>
    </div>

    <!-- 统计概览 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">评价总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.avgRating }}<span class="stat-unit">/5</span></div>
          <div class="stat-label">平均评分</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.positiveRate }}%</div>
          <div class="stat-label">好评率(≥4星)</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-value">{{ stats.commentedCount }}</div>
          <div class="stat-label">有文字评价</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card class="filter-bar">
      <el-row :gutter="16" align="middle">
        <el-col :span="4">
          <el-select v-model="sortBy" placeholder="排序方式" @change="fetchFeedbacks" style="width:100%">
            <el-option label="按时间排序" value="time" />
            <el-option label="按评分排序" value="rating" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="sortOrder" placeholder="排序方向" @change="fetchFeedbacks" style="width:100%">
            <el-option label="最新优先" value="desc" />
            <el-option label="最早优先" value="asc" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="minRating" placeholder="最低评分" clearable @change="fetchFeedbacks" style="width:100%">
            <el-option label="全部评分" :value="0" />
            <el-option label="≥ 5星" :value="5" />
            <el-option label="≥ 4星" :value="4" />
            <el-option label="≥ 3星" :value="3" />
            <el-option label="≥ 2星" :value="2" />
            <el-option label="≥ 1星" :value="1" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-button @click="fetchFeedbacks" style="width:100%">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 评价列表 -->
    <el-card>
      <!-- 加载状态 -->
      <div v-if="loading" class="state-box">
        <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
        <p>正在加载评价数据...</p>
      </div>

      <!-- 空数据 -->
      <div v-else-if="feedbacks.length === 0" class="state-box">
        <el-empty description="暂无评价数据" />
      </div>

      <!-- 列表 -->
      <div v-else class="feedback-list">
        <div v-for="fb in feedbacks" :key="fb.id" class="feedback-card">
          <div class="fb-header">
            <div class="fb-user">
              <div class="fb-avatar">{{ fb.username.charAt(0) }}</div>
              <div class="fb-userinfo">
                <span class="fb-username">{{ fb.username }}</span>
                <span class="fb-time">{{ fb.question_time }}</span>
              </div>
            </div>
            <div class="fb-rating">
              <el-rate
                :model-value="fb.rating"
                disabled
                :size="'small'"
                :colors="['#c8a45c', '#c8a45c', '#c8a45c']"
              />
              <span class="fb-rating-text" v-if="fb.rating > 0">{{ fb.rating }}/5</span>
              <span class="fb-rating-text" v-else>未评分</span>
            </div>
          </div>
          <div class="fb-body" v-if="fb.comment">
            <p class="fb-comment">{{ fb.comment }}</p>
          </div>
          <div class="fb-body" v-else>
            <p class="fb-no-comment">（仅评分，无文字评价）</p>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="feedbacks.length > 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="perPage"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchFeedbacks"
          @size-change="fetchFeedbacks"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getRouteFeedbacks } from '@/utils/api'

const route = useRoute()
const router = useRouter()

const routeId = computed(() => Number(route.params.id))
const routeName = computed(() => route.query.name || `路线#${routeId.value}`)

// ====== 数据 ======
const feedbacks = ref([])
const loading = ref(false)
const page = ref(1)
const perPage = ref(10)
const total = ref(0)

// ====== 筛选排序 ======
const sortBy = ref('time')
const sortOrder = ref('desc')
const minRating = ref(0)

// ====== 统计 ======
const stats = reactive({
  total: 0,
  avgRating: '0.0',
  positiveRate: 0,
  commentedCount: 0
})

// ====== 方法 ======
onMounted(() => {
  fetchFeedbacks()
})

async function fetchFeedbacks() {
  loading.value = true
  try {
    const res = await getRouteFeedbacks(routeId.value, {
      page: page.value,
      per_page: perPage.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
      min_rating: minRating.value
    })

    if (res.code === 200) {
      const data = res.data
      feedbacks.value = data.items || []
      total.value = data.total || 0

      // 计算统计（基于当前返回的全部数据，或重新请求全量）
      computeStats()
    } else {
      ElMessage.error(res.message || '加载评价数据失败')
    }
  } catch (e) {
    console.error('加载评价失败:', e)
    ElMessage.error('加载评价数据失败，请检查网络')
  } finally {
    loading.value = false
  }
}

async function computeStats() {
  // 请求全量数据用于统计
  try {
    const res = await getRouteFeedbacks(routeId.value, {
      page: 1,
      per_page: 9999,
      sort_by: 'time',
      sort_order: 'desc',
      min_rating: 0
    })
    if (res.code === 200) {
      const allItems = res.data.items || []
      stats.total = allItems.length

      if (allItems.length > 0) {
        const ratings = allItems.filter(f => f.rating > 0).map(f => f.rating)
        if (ratings.length > 0) {
          stats.avgRating = (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1)
        } else {
          stats.avgRating = '0.0'
        }

        const positive = allItems.filter(f => f.rating >= 4).length
        stats.positiveRate = allItems.length > 0 ? Math.round((positive / allItems.length) * 100) : 0
        stats.commentedCount = allItems.filter(f => f.comment && f.comment.trim()).length
      }
    }
  } catch (e) {
    console.error('统计计算失败:', e)
  }
}

function goBack() {
  router.push('/routes')
}
</script>

<style scoped>
.route-feedbacks {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.back-btn {
  color: #8cccd6;
  font-size: 20px;
  padding: 4px;
}

.back-btn:hover {
  color: #00e5cc;
  background: rgba(0, 229, 204, 0.08);
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #e6f7ff;
  letter-spacing: 0.5px;
}

/* 统计卡片 */
.stats-row {
  margin-bottom: 16px;
}

.stat-card {
  background: linear-gradient(135deg, rgba(10, 22, 40, 0.9) 0%, rgba(13, 26, 43, 0.9) 100%);
  border: 1px solid rgba(0, 136, 153, 0.15);
  border-radius: 10px;
  text-align: center;
  padding: 12px 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #00e5cc;
  font-variant-numeric: tabular-nums;
}

.stat-unit {
  font-size: 14px;
  color: #8cccd6;
  font-weight: 400;
}

.stat-label {
  font-size: 12px;
  color: #6b8a9a;
  margin-top: 4px;
}

/* 筛选栏 */
.filter-bar {
  margin-bottom: 16px;
  background: rgba(12, 20, 34, 0.8);
  border: 1px solid rgba(0, 136, 153, 0.12);
}

/* 状态盒子 */
.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #6b8a9a;
}

.loading-icon {
  animation: spin 1s linear infinite;
  color: #00e5cc;
  margin-bottom: 12px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 评价列表 */
.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feedback-card {
  background: rgba(12, 20, 34, 0.6);
  border: 1px solid rgba(0, 136, 153, 0.08);
  border-radius: 10px;
  padding: 16px 20px;
  transition: border-color 0.2s ease;
}

.feedback-card:hover {
  border-color: rgba(0, 229, 204, 0.2);
}

.fb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.fb-user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fb-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00e5cc, #008899);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.fb-userinfo {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fb-username {
  font-size: 14px;
  font-weight: 600;
  color: #e6f7ff;
}

.fb-time {
  font-size: 12px;
  color: #6b8a9a;
}

.fb-rating {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fb-rating-text {
  font-size: 13px;
  color: #c8a45c;
  font-weight: 600;
  min-width: 28px;
}

.fb-body {
  padding: 12px 16px;
  background: rgba(0, 229, 204, 0.04);
  border-radius: 8px;
  border-left: 2px solid rgba(0, 229, 204, 0.2);
  display: flex;
  gap: 8px;
}

.fb-comment {
  margin: 0;
  font-size: 14px;
  color: #c4d4dc;
  line-height: 1.7;
  word-break: break-word;
}

.fb-no-comment {
  margin: 0;
  font-size: 13px;
  color: #6b8a9a;
  font-style: italic;
}

/* 分页 */
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

/* Element Plus 组件暗色覆盖 */
:deep(.el-empty__description) {
  color: #6b8a9a;
}
</style>
